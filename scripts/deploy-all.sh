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
#
# Optional environment variables:
#   ARCH=amd64|arm64   Container/Fargate CPU architecture. Default: the build
#                      host's architecture (native build, no emulation). The
#                      same value drives the docker build platform AND the
#                      Fargate task definition, so they always match.
#   APP_ONLY=1         Deploy only the app path (network/security/storage/
#                      database/API/frontend) and skip the Bedrock Knowledge
#                      Base, migration-pipeline, and observability stacks.
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

# TLS mode for the API's ALB (ApiStack). Set ONE of:
#   ACM_CERT_ARN=<arn>       production: HTTPS-only ALB with your ACM certificate
#   ENABLE_HTTP_SANDBOX=1    non-production: HTTP-only ALB (no domain/cert needed)
API_CTX=()
if [ -n "${ACM_CERT_ARN:-}" ]; then
  API_CTX=(-c "acm_cert_arn=$ACM_CERT_ARN")
  echo "  API TLS: HTTPS (ACM cert)"
elif [ "${ENABLE_HTTP_SANDBOX:-}" = "1" ]; then
  API_CTX=(-c "enable_http_sandbox=1")
  echo "  API TLS: HTTP sandbox (NON-PRODUCTION — no TLS)"
else
  echo "Set ACM_CERT_ARN=<arn> for production HTTPS, or ENABLE_HTTP_SANDBOX=1 for a" >&2
  echo "non-production HTTP-only sandbox, then re-run." >&2
  exit 1
fi

# Container CPU architecture (must match between the image build and the Fargate
# task definition). Defaults to the build host's architecture for a native build.
ARCH="${ARCH:-$(uname -m)}"
case "$ARCH" in
  arm64|aarch64) ARCH=arm64 ;;
  amd64|x86_64)  ARCH=amd64 ;;
  *) echo "Unsupported ARCH: $ARCH (use amd64 or arm64)" >&2; exit 1 ;;
esac
echo "  Container architecture: $ARCH"

# app.py instantiates every stack at synth time (ApiStack included), so the TLS
# and arch context must accompany EVERY cdk invocation, not just ApiStack's.
CTX=("${API_CTX[@]}" -c "arch=$ARCH")

# --- 1. Infrastructure --------------------------------------------------------
cd "$CDK_DIR"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

echo "== cdk bootstrap =="
cdk bootstrap "aws://$ACCOUNT/$REGION" "${CTX[@]}"

echo "== cdk deploy (network / security / storage) =="
cdk deploy NetworkStack SecurityStack StorageStack \
  --require-approval never "${CTX[@]}"

# The DatabaseStack EC2 bootstrap pulls these seed files from the artifacts
# bucket at first boot (creates the app_data schema + sample data); they MUST
# be in S3 before the instance launches or the API will 500 on every endpoint.
echo "== Upload database seed SQL =="
ARTIFACTS="$(out StorageStack ArtifactsBucketName)"
[ -n "$ARTIFACTS" ] && [ "$ARTIFACTS" != "None" ] || { echo "No ArtifactsBucketName output."; exit 1; }
aws s3 cp "$ROOT/infrastructure/seed-sql/app_data_packages.sql" \
  "s3://$ARTIFACTS/input/plsql-stubs/app_data_packages.sql"
aws s3 cp "$ROOT/infrastructure/seed-sql/load_hr_schema.sql" \
  "s3://$ARTIFACTS/input/schema/load_hr_schema.sql"
aws s3 cp "$ROOT/infrastructure/seed-sql/apex_sample_seed.sql" \
  "s3://$ARTIFACTS/input/schema/apex_sample_seed.sql"

echo "== cdk deploy (database) =="
# After DatabaseStack, patch the DB secret's host with the instance IP: the
# secret is created by SecurityStack before the DB exists (host=TO_BE_SET),
# and the pipeline Lambdas read host/port/service from the secret (BUG-20).
patch_secret_host() {
  local ip; ip="$(out DatabaseStack OraclePrivateIp)"
  [ -n "$ip" ] && [ "$ip" != "None" ] || { echo "No OraclePrivateIp output."; exit 1; }
  local cur new
  cur="$(aws secretsmanager get-secret-value --region "$REGION" \
    --secret-id oracle-modernization/oracle/admin --query SecretString --output text)"
  new="$(printf '%s' "$cur" | DB_IP="$ip" python3 -c \
    'import json,os,sys; d=json.load(sys.stdin); d["host"]=os.environ["DB_IP"]; print(json.dumps(d))')"
  aws secretsmanager put-secret-value --region "$REGION" \
    --secret-id oracle-modernization/oracle/admin \
    --secret-string "$new" --query VersionId --output text >/dev/null
  echo "secret host -> $ip"
}
cdk deploy DatabaseStack --require-approval never "${CTX[@]}"
patch_secret_host

if [ "${APP_ONLY:-}" = "1" ]; then
  echo "== APP_ONLY=1 — skipping BedrockKBStack / PipelineStack / ObservabilityStack =="
else
  echo "== cdk deploy (knowledge base / pipeline / observability) =="
  cdk deploy BedrockKBStack PipelineStack ObservabilityStack \
    --require-approval never "${CTX[@]}"
fi

# --- 2. .NET API image -> ECR + ApiStack -------------------------------------
REPO_URI="$(out StorageStack DotnetRepoUri)"
[ -n "$REPO_URI" ] && [ "$REPO_URI" != "None" ] || { echo "No DotnetRepoUri output."; exit 1; }

echo "== Build & push .NET API image =="
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
# The image platform matches the ApiStack task definition via -c arch (BUG-13).
docker build --platform "linux/$ARCH" -t "$REPO_URI:latest" "$ROOT/app/dotnet_api"
docker push "$REPO_URI:latest"

echo "== Deploy ApiStack (ALB + Fargate) =="
cdk deploy ApiStack --require-approval never "${CTX[@]}"
API_URL="$(out ApiStack ApiUrl)"

echo "== Wait for API health =="
for i in $(seq 1 20); do
  curl -fsS "$API_URL/health" >/dev/null 2>&1 && { echo "  healthy"; break; }
  echo "  waiting ($i/20)..."; sleep 15
done

# --- 3. CloudFront same-origin /api/* proxy ----------------------------------
ALB_DNS="${API_URL#http://}"; ALB_DNS="${ALB_DNS#https://}"
echo "== Redeploy StorageStack with /api/* proxy -> $ALB_DNS =="
cdk deploy StorageStack --require-approval never -c "api_alb_dns=$ALB_DNS" "${CTX[@]}"

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
DIST_ID="$(out StorageStack CloudFrontDistributionId)"
aws s3 sync dist/*/browser "s3://$BUCKET" --delete
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*' >/dev/null

CF_DOMAIN="$(out StorageStack CloudFrontDomain)"
echo
echo "Done. Open: https://$CF_DOMAIN   (routes: /orders, /accounts, /reports/accounts)"
echo "Run the migration pipeline separately: see pipeline/README.md"
