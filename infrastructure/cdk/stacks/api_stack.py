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

        # An ACM certificate is required — plain HTTP is not a shipped default.
        # Provide the ARN via: cdk deploy -c acm_cert_arn=<arn>
        cert_arn = self.node.try_get_context("acm_cert_arn")
        if not cert_arn:
            raise ValueError(
                "Provide an ACM certificate ARN via '-c acm_cert_arn=<arn>' "
                "— the ALB is HTTPS-only; plain HTTP is not a shipped default."
            )
        certificate = acm.Certificate.from_certificate_arn(
            self, "ApiCert", cert_arn)

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
        # HTTPS is required; redirect_http=True adds an HTTP:80 listener that
        # issues a 301 redirect to HTTPS:443 (the redirect listener is why
        # port 80 remains open on the ALB SG in NetworkStack).
        self.service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "ApiService",
            service_name=f"{prefix}-dotnet-api",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            load_balancer=alb,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            listener_port=443,
            certificate=certificate,
            redirect_http=True,
            security_groups=[network.ecs_api_sg],
            task_subnets=network.private_subnets,
            assign_public_ip=False,
        )
        self.service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
        )

        CfnOutput(self, "ApiUrl",
                  value=f"https://{self.service.load_balancer.load_balancer_dns_name}")
