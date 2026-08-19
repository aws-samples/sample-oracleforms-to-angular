# One-command deploy for the sample (Windows / PowerShell).
# Mirror of deploy-all.sh. Prereqs: awscli v2, Node.js >= 18, Python >= 3.11,
# .NET SDK 8, Docker Desktop, AWS CDK CLI (npm i -g aws-cdk).
# Configure AWS credentials first, and copy .env.example to .env.
$ErrorActionPreference = "Stop"

$Region = if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-1" }
$Root   = Split-Path -Parent $PSScriptRoot
$CdkDir = Join-Path $Root "infrastructure/cdk"

function Out-Val($Stack, $Key) {
  aws cloudformation describe-stacks --region $Region --stack-name $Stack `
    --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue" --output text
}

Write-Host "== Preflight =="
foreach ($bin in @("aws","cdk","docker","node","npm","python","dotnet")) {
  if (-not (Get-Command $bin -ErrorAction SilentlyContinue)) { throw "Missing tool: $bin" }
}
$Account = (aws sts get-caller-identity --query Account --output text)
Write-Host "  Account: $Account   Region: $Region"

# --- 1. Infrastructure -------------------------------------------------------
Set-Location $CdkDir
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".venv/Scripts/Activate.ps1"
pip install -q -r requirements.txt

Write-Host "== cdk bootstrap =="
cdk bootstrap "aws://$Account/$Region"

Write-Host "== cdk deploy (infrastructure) =="
cdk deploy NetworkStack SecurityStack StorageStack DatabaseStack `
  BedrockKBStack PipelineStack ObservabilityStack --require-approval never

# --- 2. .NET API image -> ECR + ApiStack ------------------------------------
$RepoUri = Out-Val "StorageStack" "DotnetRepoUri"
Write-Host "== Build & push .NET API image =="
aws ecr get-login-password --region $Region |
  docker login --username AWS --password-stdin "$Account.dkr.ecr.$Region.amazonaws.com"
docker build --platform linux/amd64 -t "$RepoUri:latest" (Join-Path $Root "app/dotnet_api")
docker push "$RepoUri:latest"

Write-Host "== Deploy ApiStack =="
cdk deploy ApiStack --require-approval never
$ApiUrl = Out-Val "ApiStack" "ApiUrl"

# --- 3. CloudFront same-origin /api/* proxy ---------------------------------
$AlbDns = $ApiUrl -replace '^https?://',''
Write-Host "== Redeploy StorageStack with /api/* proxy -> $AlbDns =="
cdk deploy StorageStack --require-approval never -c "api_alb_dns=$AlbDns"

# --- 4. Angular SPA -> S3 + CloudFront --------------------------------------
Write-Host "== Build & ship Angular SPA =="
Set-Location (Join-Path $Root "app/angular_app")
if (-not (Test-Path "node_modules")) { npm install }
$EnvFile = "src/environments/environment.ts"
(Get-Content $EnvFile) -replace '__API_BASE_URL__','' | Set-Content $EnvFile
npm run build
$Bucket = Out-Val "StorageStack" "FrontendBucketName"
$DistId = Out-Val "StorageStack" "DistributionId"
aws s3 sync (Get-ChildItem dist -Directory | Select-Object -First 1).FullName/browser "s3://$Bucket" --delete
aws cloudfront create-invalidation --distribution-id $DistId --paths "/*" | Out-Null

$CfDomain = Out-Val "StorageStack" "DistributionDomain"
Write-Host "Done. Open: https://$CfDomain"
