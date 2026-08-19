#!/usr/bin/env bash
# One-command deploy for the sample.
#
#   1. Deploy the infrastructure stacks with AWS CDK (network, security, storage,
#      database, Bedrock Knowledge Base, migration pipeline, observability).
#   2. Build the .NET API container, push to Amazon ECR, deploy the API stack
#      (Application Load Balancer + Amazon ECS Fargate).
#   3. Wire the ALB into CloudFront as a same-origin /api/* proxy.
#   4. Build the Angular SPA, sync to Amazon S3, invalidate CloudFront.
#
# Prereqs: awscli v2, Node.js >= 18, Python >= 3.11, .NET SDK 8, Docker, and the
# AWS CDK CLI (`npm i -g aws-cdk`). Configure AWS credentials first, and copy
# .env.example to .env (values are read from your environment).
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDK_DIR="$ROOT/infrastructure/cdk"

out() { # stack, output-key
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text
}

echo "== Preflight =="
for bin in aws cdk docker node npm python3 dotnet; do
  command -v "$bin" >/dev/null 2>&1 || { echo "Missing required tool: $bin"; exit 1; }
done
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
echo "  Account: $ACCOUNT   Region: $REGION"

# --- 1. Infrastructure --------------------------------------------------------
cd "$CDK_DIR"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

echo "== cdk bootstrap =="
cdk bootstrap "aws://$ACCOUNT/$REGION"

echo "== cdk deploy (infrastructure) =="
cdk deploy \
  NetworkStack SecurityStack StorageStack DatabaseStack \
  BedrockKBStack PipelineStack ObservabilityStack \
  --require-approval never

# --- 2. .NET API image -> ECR + ApiStack -------------------------------------
REPO_URI="$(out StorageStack DotnetRepoUri)"
[ -n "$REPO_URI" ] && [ "$REPO_URI" != "None" ] || { echo "No DotnetRepoUri output."; exit 1; }

echo "== Build & push .NET API image =="
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
# Fargate runs linux/amd64.
docker build --platform linux/amd64 -t "$REPO_URI:latest" "$ROOT/app/dotnet_api"
docker push "$REPO_URI:latest"

echo "== Deploy ApiStack (ALB + Fargate) =="
cdk deploy ApiStack --require-approval never
API_URL="$(out ApiStack ApiUrl)"

echo "== Wait for API health =="
for i in $(seq 1 20); do
  curl -fsS "$API_URL/health" >/dev/null 2>&1 && { echo "  healthy"; break; }
  echo "  waiting ($i/20)..."; sleep 15
done

# --- 3. CloudFront same-origin /api/* proxy ----------------------------------
ALB_DNS="${API_URL#http://}"; ALB_DNS="${ALB_DNS#https://}"
echo "== Redeploy StorageStack with /api/* proxy -> $ALB_DNS =="
cdk deploy StorageStack --require-approval never -c "api_alb_dns=$ALB_DNS"

# --- 4. Angular SPA -> S3 + CloudFront ---------------------------------------
echo "== Build & ship Angular SPA =="
cd "$ROOT/app/angular_app"
[ -d node_modules ] || npm install
# API is same-origin via the CloudFront /api/* proxy, so the base URL is empty.
ENV_FILE="src/environments/environment.ts"
sed -i.bak "s#__API_BASE_URL__##" "$ENV_FILE"
npm run build
mv "$ENV_FILE.bak" "$ENV_FILE"

BUCKET="$(out StorageStack FrontendBucketName)"
DIST_ID="$(out StorageStack DistributionId)"
aws s3 sync dist/*/browser "s3://$BUCKET" --delete
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*' >/dev/null

CF_DOMAIN="$(out StorageStack DistributionDomain)"
echo
echo "Done. Open: https://$CF_DOMAIN   (routes: /accounts, /reports/accounts)"
echo "Run the migration pipeline separately: see pipeline/README.md"
