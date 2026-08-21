"""ApiStack — the generated .NET 8 API on ECS Fargate behind a public ALB.

The task pulls its Oracle connection string from Secrets Manager. Fargate (not
App Runner) is used because the Oracle EC2 lives in an isolated subnet that
App Runner cannot reach. Deploy this after the .NET image is pushed to ECR
(scripts/05_deploy_apps.sh).
"""
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_certificatemanager as acm,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
)
from constructs import Construct


class ApiStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, prefix: str,
                 network, security, storage, database, **kwargs):
        super().__init__(scope, cid, **kwargs)
        self.prefix = prefix

        # TLS posture. Production default: HTTPS-only ALB with an ACM certificate,
        #   cdk deploy -c acm_cert_arn=<arn>
        # Sandbox escape hatch (NON-PRODUCTION): -c enable_http_sandbox=1 deploys an
        # HTTP-only ALB so the sample can run without owning a domain / ACM cert.
        # Never use the sandbox toggle for anything internet-facing with real data.
        cert_arn = self.node.try_get_context("acm_cert_arn")
        http_sandbox = str(
            self.node.try_get_context("enable_http_sandbox") or ""
        ).lower() in ("1", "true", "yes")
        if not cert_arn and not http_sandbox:
            raise ValueError(
                "Provide an ACM certificate ARN via '-c acm_cert_arn=<arn>' "
                "(the ALB is HTTPS-only by default). For a non-production sandbox "
                "without a domain/cert, pass '-c enable_http_sandbox=1' to deploy "
                "an HTTP-only ALB."
            )
        certificate = (
            acm.Certificate.from_certificate_arn(self, "ApiCert", cert_arn)
            if cert_arn else None
        )

        cluster = ecs.Cluster(
            self, "Cluster",
            cluster_name=f"{prefix}-cluster",
            vpc=network.vpc,
            container_insights=True,
        )

        secret = security.oracle_secret
        # Build the ADO.NET connection string from the secret fields + the
        # Oracle private IP (known at synth via DatabaseStack).
        oracle_host = database.private_ip

        task_def = ecs.FargateTaskDefinition(
            self, "ApiTaskDef",
            family=f"{prefix}-dotnet-api",
            cpu=512,
            memory_limit_mib=1024,
            # CPU architecture MUST match the pushed container image (BUG-13).
            # deploy-all.sh passes -c arch=<amd64|arm64> derived from the build
            # host so the image is always built natively. Default: amd64.
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=(
                    ecs.CpuArchitecture.ARM64
                    if str(self.node.try_get_context("arch") or "amd64").lower()
                    in ("arm64", "aarch64")
                    else ecs.CpuArchitecture.X86_64
                ),
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
            ),
            task_role=security.ecs_task_role,
            # Execution role owned by SecurityStack (holds the secret/KMS grants)
            # to avoid a SecurityStack <-> ApiStack dependency cycle.
            execution_role=security.ecs_execution_role,
        )

        container = task_def.add_container(
            "api",
            # Reference by URI rather than from_ecr_repository: the latter grants
            # pull to the (SecurityStack-owned) execution role, referencing the
            # StorageStack repo and cycling with StorageStack's dependency on the
            # KMS key. The managed execution policy already allows ECR pull.
            image=ecs.ContainerImage.from_registry(
                f"{storage.dotnet_repo.repository_uri}:latest"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="dotnet-api",
                # Use the SecurityStack-owned log group (see EcsExecutionRole).
                log_group=security.api_log_group,
            ),
            environment={
                "ORACLE_HOST": oracle_host,
                "ORACLE_PORT": "1521",
                "ORACLE_SERVICE": "XEPDB1",
                "ASPNETCORE_URLS": "http://+:8080",
            },
            secrets={
                # Injected as env vars from the JSON secret fields.
                "ORACLE_USER": ecs.Secret.from_secrets_manager(secret, "username"),
                "ORACLE_PASSWORD": ecs.Secret.from_secrets_manager(secret, "password"),
            },
        )
        container.add_port_mappings(ecs.PortMapping(container_port=8080))

        # Pre-create the ALB with the alb_sg defined in NetworkStack. Letting the
        # pattern auto-create the ALB SG would make NetworkStack depend on
        # ApiStack (to add the alb->ecs ingress rule), which cycles because
        # ApiStack already depends on NetworkStack. NetworkStack already owns the
        # alb_sg -> ecs_api_sg:8080 rule, so all SG wiring stays intra-stack.
        alb = elbv2.ApplicationLoadBalancer(
            self, "ApiAlb",
            vpc=network.vpc,
            internet_facing=True,
            security_group=network.alb_sg,
            vpc_subnets=network.public_subnets,
        )

        # Fargate service fronted by the internet-facing ALB above.
        common = dict(
            service_name=f"{prefix}-dotnet-api",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            load_balancer=alb,
            security_groups=[network.ecs_api_sg],
            task_subnets=network.private_subnets,
            assign_public_ip=False,
        )
        if certificate is not None:
            # Production posture: HTTPS-only; redirect_http adds an HTTP:80 ->
            # HTTPS:443 301 redirect (why port 80 stays open on the ALB SG).
            self.service = ecs_patterns.ApplicationLoadBalancedFargateService(
                self, "ApiService",
                protocol=elbv2.ApplicationProtocol.HTTPS,
                listener_port=443,
                certificate=certificate,
                redirect_http=True,
                **common,
            )
            scheme = "https"
        else:
            # NON-PRODUCTION sandbox: HTTP-only ALB on port 80, no cert/redirect.
            self.service = ecs_patterns.ApplicationLoadBalancedFargateService(
                self, "ApiService",
                protocol=elbv2.ApplicationProtocol.HTTP,
                listener_port=80,
                **common,
            )
            scheme = "http"
        self.service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
        )

        CfnOutput(self, "ApiUrl",
                  value=f"{scheme}://{self.service.load_balancer.load_balancer_dns_name}")
