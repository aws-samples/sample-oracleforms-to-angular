"""NetworkStack — VPC, subnets, NAT, VPC endpoints, and security groups.

Three subnet tiers:
  - PUBLIC            : ALB + NAT gateway
  - PRIVATE_WITH_EGRESS : ECS Fargate (.NET API), pipeline Lambdas, Oracle EC2
                          (Oracle needs NAT egress to pull the XE image + clone
                          the HR sample schema; no public IP, admin via SSM)
  - PRIVATE_ISOLATED  : reserved (unused by the current POC)

Interface endpoints keep Bedrock/Secrets/ECR/SSM/Logs traffic on the AWS
backbone; an S3 gateway endpoint avoids NAT charges for artifact traffic.
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_logs as logs,
)
from constructs import Construct


class NetworkStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, prefix: str, **kwargs):
        super().__init__(scope, cid, **kwargs)
        self.prefix = prefix

        self.vpc = ec2.Vpc(
            self, "Vpc",
            vpc_name=f"{prefix}-vpc",
            max_azs=2,
            nat_gateways=1,  # single NAT to keep POC cost down
            ip_addresses=ec2.IpAddresses.cidr("10.42.0.0/16"),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=23,
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # --- Security groups -------------------------------------------------
        # Oracle EC2: only the API and the pipeline Lambdas may reach 1521.
        self.oracle_sg = ec2.SecurityGroup(
            self, "OracleSg", vpc=self.vpc,
            security_group_name=f"{prefix}-oracle-sg",
            description="Oracle XE 21c - 1521 from app/pipeline only",
            allow_all_outbound=True,
        )
        self.lambda_sg = ec2.SecurityGroup(
            self, "LambdaSg", vpc=self.vpc,
            security_group_name=f"{prefix}-lambda-sg",
            description="Pipeline Lambdas",
            allow_all_outbound=True,
        )
        self.ecs_api_sg = ec2.SecurityGroup(
            self, "EcsApiSg", vpc=self.vpc,
            security_group_name=f"{prefix}-ecs-api-sg",
            description=".NET API Fargate tasks",
            allow_all_outbound=True,
        )
        self.alb_sg = ec2.SecurityGroup(
            self, "AlbSg", vpc=self.vpc,
            security_group_name=f"{prefix}-alb-sg",
            description="Public ALB for the .NET API",
            allow_all_outbound=True,
        )

        # Ingress rules (least privilege, SG-to-SG).
        self.oracle_sg.add_ingress_rule(
            self.lambda_sg, ec2.Port.tcp(1521), "Oracle from pipeline Lambdas")
        self.oracle_sg.add_ingress_rule(
            self.ecs_api_sg, ec2.Port.tcp(1521), "Oracle from .NET API")
        self.ecs_api_sg.add_ingress_rule(
            self.alb_sg, ec2.Port.tcp(8080), ".NET API from ALB")
        self.alb_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS from anywhere")
        # Port 80 is kept open only to serve the HTTP→HTTPS redirect listener;
        # it does not carry application traffic.
        self.alb_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP redirect to HTTPS")

        # --- VPC endpoints ---------------------------------------------------
        # Gateway endpoint for S3 (free, avoids NAT for artifact traffic).
        self.vpc.add_gateway_endpoint(
            "S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3)

        interface_services = {
            "BedrockRuntime": ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
            "SecretsManager": ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            "EcrApi": ec2.InterfaceVpcEndpointAwsService.ECR,
            "EcrDkr": ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            "Ssm": ec2.InterfaceVpcEndpointAwsService.SSM,
            "SsmMessages": ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
            "Ec2Messages": ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
            "CloudWatchLogs": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
        }
        # Endpoints live in the private-with-egress subnets; the isolated Oracle
        # box reaches SSM/Secrets through them without a NAT route.
        endpoint_subnets = ec2.SubnetSelection(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        for name, svc in interface_services.items():
            self.vpc.add_interface_endpoint(
                f"{name}Endpoint", service=svc, subnets=endpoint_subnets,
                private_dns_enabled=True,
            )

        # --- VPC flow logs ---------------------------------------------------
        # Owned here (not in ObservabilityStack) because add_flow_log mutates the
        # VPC. If ObservabilityStack added it, NetworkStack would depend on
        # ObservabilityStack, which already depends (transitively via Pipeline/
        # Api) on NetworkStack -> cycle.
        flow_log_group = logs.LogGroup(
            self, "VpcFlowLogs",
            log_group_name=f"/{prefix}/vpc-flow-logs",
            retention=logs.RetentionDays.ONE_WEEK,
        )
        self.vpc.add_flow_log(
            "FlowLog",
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(flow_log_group),
            traffic_type=ec2.FlowLogTrafficType.ALL,
        )

    # Convenience selections used by dependent stacks.
    @property
    def isolated_subnets(self) -> ec2.SubnetSelection:
        return ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)

    @property
    def private_subnets(self) -> ec2.SubnetSelection:
        return ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)

    @property
    def public_subnets(self) -> ec2.SubnetSelection:
        return ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
