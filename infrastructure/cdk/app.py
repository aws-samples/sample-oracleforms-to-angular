#!/usr/bin/env python3
"""CDK app entry point for the Oracle modernization sample POC.

Instantiates the eight stacks and wires their dependencies via props objects
(not CfnImportValue) so the whole app deploys from one synthesis. Region is
pinned to us-east-1 for Bedrock model + Knowledge Base availability.

Deploy order (CDK resolves the dependency edges automatically):
    NetworkStack -> SecurityStack -> {StorageStack, DatabaseStack}
                 -> BedrockKBStack -> PipelineStack -> ApiStack -> ObservabilityStack
"""
import os

import aws_cdk as cdk

from stacks.network_stack import NetworkStack
from stacks.security_stack import SecurityStack
from stacks.storage_stack import StorageStack
from stacks.database_stack import DatabaseStack
from stacks.bedrock_kb_stack import BedrockKbStack
from stacks.pipeline_stack import PipelineStack
from stacks.api_stack import ApiStack
from stacks.observability_stack import ObservabilityStack

# Region is fixed for Bedrock/KB availability; account comes from the CLI creds
# (your AWS account) unless CDK_DEFAULT_ACCOUNT is set.
ENV = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

# Prefix keeps resource names unique/greppable for this POC.
PREFIX = "oracle-modernization"

app = cdk.App()

network = NetworkStack(app, "NetworkStack", prefix=PREFIX, env=ENV)

security = SecurityStack(
    app, "SecurityStack", prefix=PREFIX, network=network, env=ENV
)

storage = StorageStack(
    app, "StorageStack", prefix=PREFIX, security=security, env=ENV
)

database = DatabaseStack(
    app, "DatabaseStack", prefix=PREFIX, network=network, security=security,
    storage=storage, env=ENV,
)

bedrock_kb = BedrockKbStack(
    app, "BedrockKBStack", prefix=PREFIX, network=network, security=security,
    storage=storage, env=ENV,
)

pipeline = PipelineStack(
    app, "PipelineStack", prefix=PREFIX, network=network, security=security,
    storage=storage, database=database, bedrock_kb=bedrock_kb, env=ENV,
)

api = ApiStack(
    app, "ApiStack", prefix=PREFIX, network=network, security=security,
    storage=storage, database=database, env=ENV,
)

ObservabilityStack(
    app, "ObservabilityStack", prefix=PREFIX,
    pipeline=pipeline, api=api, env=ENV,
)

# Tag everything for cost tracking + easy teardown identification.
cdk.Tags.of(app).add("project", "oracle-modernization-poc")
cdk.Tags.of(app).add("environment", "poc")
cdk.Tags.of(app).add("owner", "oracle-modernization-poc")

app.synth()
