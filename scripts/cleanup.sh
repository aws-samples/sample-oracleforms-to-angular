#!/usr/bin/env bash
# Tear down everything this sample created. Destroys all CDK stacks.
#
# S3 buckets and the ECR repo may need to be emptied first if they are non-empty
# and not configured for auto-delete; this script empties the frontend + KB
# buckets before destroying.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDK_DIR="$ROOT/infrastructure/cdk"

out() { aws cloudformation describe-stacks --region "$REGION" --stack-name "$1" \
  --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text 2>/dev/null || true; }

echo "== Emptying S3 buckets (best effort) =="
for b in "$(out StorageStack FrontendBucketName)" "$(out BedrockKBStack KbSourceBucketName)"; do
  [ -n "$b" ] && [ "$b" != "None" ] && aws s3 rm "s3://$b" --recursive --region "$REGION" || true
done

echo "== cdk destroy --all =="
cd "$CDK_DIR"
[ -d .venv ] && source .venv/bin/activate
cdk destroy --all --force

echo
echo "Stacks destroyed. If you provisioned an OpenSearch Serverless collection or"
echo "Bedrock Knowledge Base outside CDK, verify they are removed to stop charges."
