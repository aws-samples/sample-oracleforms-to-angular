"""StorageStack — S3 buckets, CloudFront (frontend), and the ECR repo.

All resources use RemovalPolicy.DESTROY + auto-delete/empty for clean POC
teardown. Buckets are SSE-KMS with the CMK from SecurityStack. The frontend
bucket is private and served only through CloudFront (Origin Access Control).
"""
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnOutput,
    aws_s3 as s3,
    aws_ecr as ecr,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, prefix: str, security, **kwargs):
        super().__init__(scope, cid, **kwargs)
        self.prefix = prefix
        key = security.kms_key

        # --- Artifact bucket (pipeline inputs + intermediate + generated) ----
        self.artifacts_bucket = s3.Bucket(
            self, "ArtifactsBucket",
            bucket_name=f"{prefix}-artifacts-{Stack.of(self).account}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            lifecycle_rules=[s3.LifecycleRule(
                noncurrent_version_expiration=Duration.days(30))],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- Frontend bucket (Angular static site) --------------------------
        self.frontend_bucket = s3.Bucket(
            self, "FrontendBucket",
            bucket_name=f"{prefix}-frontend-{Stack.of(self).account}",
            encryption=s3.BucketEncryption.S3_MANAGED,  # served via CF, SSE-S3 is fine
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # The .NET API's ALB is internet-facing but HTTP-only, while CloudFront
        # serves the SPA over HTTPS. A browser on the HTTPS site calling the HTTP
        # ALB directly is blocked as mixed content. Fix (AWS-native, no cert on
        # the ALB): make CloudFront a same-origin reverse proxy — a `/api/*`
        # behavior forwarding to the ALB as a second origin. Angular then calls
        # relative `/api/...` (same origin as the page), so there is no
        # mixed-content block and no CORS.
        #
        # The ALB DNS is passed via context (-c api_alb_dns=<dns>) as a literal
        # string, NOT read from ApiStack: ApiStack already depends on StorageStack
        # (ECR repo), so a construct reference the other way would form a
        # dependency cycle. A plain string creates no cross-stack edge. Same
        # toggle pattern as ObservabilityStack's detach_pipeline_metric.
        api_alb_dns = self.node.try_get_context("api_alb_dns")

        additional_behaviors = {}
        if api_alb_dns:
            additional_behaviors["/api/*"] = cloudfront.BehaviorOptions(
                origin=origins.HttpOrigin(
                    api_alb_dns,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                    http_port=80,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                # An API is dynamic: never cache, and forward the full request
                # (methods, headers, query, body) to the origin.
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            )

        # SPA deep-link routing. NOT done via distribution-wide custom error
        # responses (404/403 -> /index.html): those apply to EVERY origin,
        # including the /api/* ALB origin, so a genuine API 404/403 would be
        # silently rewritten to the SPA shell with a 200 — masking real errors
        # from any client. Instead a CloudFront Function on the S3 (default)
        # behavior only rewrites extension-less navigation requests to
        # /index.html. The /api/* behavior has no such function, so API
        # responses pass through with their true status.
        spa_router = cloudfront.Function(
            self, "SpaRouterFn",
            comment=f"{prefix} SPA fallback (S3 behavior only)",
            code=cloudfront.FunctionCode.from_inline(
                "function handler(event) {\n"
                "  var req = event.request;\n"
                "  var uri = req.uri;\n"
                "  // Static assets (contain a dot in the last segment) pass\n"
                "  // through; extension-less paths are SPA routes -> index.html.\n"
                "  var last = uri.split('/').pop();\n"
                "  if (last.indexOf('.') === -1) { req.uri = '/index.html'; }\n"
                "  return req;\n"
                "}\n"
            ),
        )

        # CloudFront with Origin Access Control.
        self.distribution = cloudfront.Distribution(
            self, "FrontendDistribution",
            comment=f"{prefix} Angular frontend",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    self.frontend_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                function_associations=[cloudfront.FunctionAssociation(
                    function=spa_router,
                    event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                )],
            ),
            additional_behaviors=additional_behaviors,
        )

        # --- ECR repo for the .NET API image --------------------------------
        self.dotnet_repo = ecr.Repository(
            self, "DotnetApiRepo",
            repository_name=f"{prefix}-dotnet-api",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
            image_scan_on_push=True,
        )

        CfnOutput(self, "ArtifactsBucketName", value=self.artifacts_bucket.bucket_name)
        CfnOutput(self, "FrontendBucketName", value=self.frontend_bucket.bucket_name)
        CfnOutput(self, "CloudFrontDomain",
                  value=self.distribution.distribution_domain_name)
        CfnOutput(self, "CloudFrontDistributionId",
                  value=self.distribution.distribution_id)
        CfnOutput(self, "DotnetRepoUri", value=self.dotnet_repo.repository_uri)
