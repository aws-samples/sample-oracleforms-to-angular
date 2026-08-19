#!/bin/bash
# Build the Angular app (same-origin API) and ship to S3 + invalidate CloudFront.
# Used by run_pipeline.py Stage 4 — fast (~1 min), no backend rollout.
#
# Reads target resources from the environment (see .env.example):
#   FRONTEND_BUCKET     - S3 bucket serving the SPA
#   CF_DISTRIBUTION_ID  - CloudFront distribution to invalidate
#   AWS_REGION          - defaults to us-east-1
set -e

REGION="${AWS_REGION:-us-east-1}"
: "${FRONTEND_BUCKET:?set FRONTEND_BUCKET (S3 bucket serving the SPA)}"
: "${CF_DISTRIBUTION_ID:?set CF_DISTRIBUTION_ID (CloudFront distribution id)}"

cd "$(dirname "$0")/angular_app"

# API is reached same-origin via the CloudFront /api/* proxy, so the base URL is empty.
ENV_FILE=src/environments/environment.ts
cp "$ENV_FILE" "$ENV_FILE.bak"
sed "s#__API_BASE_URL__##g" "$ENV_FILE.bak" > "$ENV_FILE"
npx --yes @angular/cli@17 build --configuration production 2>&1 | tail -5
RC=${PIPESTATUS[0]}
mv "$ENV_FILE.bak" "$ENV_FILE"
[ "$RC" = "0" ] || { echo "NG BUILD FAILED"; exit 1; }

DIST=$(find dist -type d -name browser | head -1)
aws s3 sync "$DIST" "s3://${FRONTEND_BUCKET}" --delete --region "$REGION" >/dev/null
aws cloudfront create-invalidation --distribution-id "$CF_DISTRIBUTION_ID" --paths '/*' \
  --region "$REGION" --query 'Invalidation.Status' --output text
echo "FRONTEND_DEPLOYED"
