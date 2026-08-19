"""PipelineStack — the AI migration pipeline: 9 Lambdas + Step Functions.

Each pipeline step is a Lambda container image (they need the Python `oracledb`
thin client and/or bedrock helpers bundled). The Express state machine chains
them; payloads carry S3 keys only (never file bodies) to stay under the 256 KB
Step Functions limit.

Flow:
  IngestForms -> IngestPLSQL -> AnalyseWithBedrock -> GenerateOpenAPI
    -> Parallel(GenerateAngular, GenerateDotNet)
    -> ValidateBehavioural -> GenerateIntegrationTests
    -> TriggerKBSync -> PublishSummary
"""
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_logs as logs,
    aws_sns as sns,
)
from constructs import Construct

# Model ids centralised so every step is consistent with the project standard.
CLAUDE_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
CLAUDE_LARGE_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"  # 1M ctx, big inputs


class PipelineStack(Stack):
    STEPS = [
        "ingest_forms", "ingest_plsql", "analyse_bedrock", "generate_openapi",
        "generate_angular", "generate_dotnet", "validate_behavioural",
        "generate_tests", "trigger_kb_sync",
    ]

    def __init__(self, scope: Construct, cid: str, *, prefix: str,
                 network, security, storage, database, bedrock_kb, **kwargs):
        super().__init__(scope, cid, **kwargs)
        self.prefix = prefix

        # The pipeline Lambdas read the committed legacy source under input/
        # and read/write their run artifacts under pipeline/. Granted as an
        # inline Policy created HERE (not storage.artifacts_bucket.grant_*
        # in SecurityStack): a grant in SecurityStack would pull the
        # StorageStack bucket ARN into SecurityStack and cycle (StorageStack
        # already depends on SecurityStack's KMS key). This stack depends on
        # both, so an inline Policy is cycle-free. KMS encrypt/decrypt for the
        # SSE-KMS bucket is already granted on the role in SecurityStack.
        iam.Policy(
            self, "PipelineArtifactsRwPolicy",
            roles=[security.pipeline_lambda_role],
            statements=[
                iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:PutObject"],
                    resources=[
                        f"{storage.artifacts_bucket.bucket_arn}/input/*",
                        f"{storage.artifacts_bucket.bucket_arn}/pipeline/*",
                    ],
                ),
                iam.PolicyStatement(
                    actions=["s3:ListBucket"],
                    resources=[storage.artifacts_bucket.bucket_arn],
                    conditions={"StringLike": {
                        "s3:prefix": ["input/*", "pipeline/*"]}},
                ),
            ],
        )

        common_env = {
            "ARTIFACTS_BUCKET": storage.artifacts_bucket.bucket_name,
            "ORACLE_SECRET_ARN": security.oracle_secret.secret_arn,
            "CLAUDE_MODEL_ID": CLAUDE_MODEL_ID,
            "CLAUDE_LARGE_MODEL_ID": CLAUDE_LARGE_MODEL_ID,
            "KB_ID": bedrock_kb.knowledge_base_id,
            "KB_DATA_SOURCE_ID": bedrock_kb.data_source_id,
        }

        # --- One Lambda container function per step -------------------------
        self.functions = {}
        for step in self.STEPS:
            fn = _lambda.DockerImageFunction(
                self, f"Fn{self._camel(step)}",
                function_name=f"{prefix}-{step.replace('_', '-')}",
                code=_lambda.DockerImageCode.from_image_asset(
                    directory="../pipeline", file=f"{step}/Dockerfile"),
                # Images are built on the local Docker host; match the Lambda
                # architecture to the build arch (arm64 on Apple Silicon /
                # Graviton). Mismatch causes Runtime.ProcessSpawnFailed.
                architecture=_lambda.Architecture.ARM_64,
                role=security.pipeline_lambda_role,
                vpc=network.vpc,
                vpc_subnets=network.private_subnets,
                security_groups=[network.lambda_sg],
                timeout=Duration.minutes(15),
                memory_size=1024,
                environment=common_env,
            )
            self.functions[step] = fn

        log_group = logs.LogGroup(
            self, "PipelineLogs",
            log_group_name=f"/{prefix}/pipeline",
            retention=logs.RetentionDays.ONE_MONTH,
        )
        self.topic = sns.Topic(
            self, "SummaryTopic", topic_name=f"{prefix}-pipeline-summary")

        # --- State machine definition ---------------------------------------
        def task(step, result_path):
            return tasks.LambdaInvoke(
                self, f"Task{self._camel(step)}",
                lambda_function=self.functions[step],
                payload_response_only=True,
                result_path=result_path,
                retry_on_service_exceptions=True,
            )

        ingest_forms = task("ingest_forms", "$.forms")
        ingest_plsql = task("ingest_plsql", "$.plsql")
        analyse = task("analyse_bedrock", "$.analysis")
        gen_openapi = task("generate_openapi", "$.openapi")
        gen_angular = task("generate_angular", "$.angular")
        gen_dotnet = task("generate_dotnet", "$.dotnet")
        validate = task("validate_behavioural", "$.validation")
        gen_tests = task("generate_tests", "$.tests")
        kb_sync = task("trigger_kb_sync", "$.kb")

        publish = tasks.SnsPublish(
            self, "PublishSummary",
            topic=self.topic,
            message=sfn.TaskInput.from_json_path_at("$"),
            subject="Oracle modernization pipeline complete",
        )

        # Generate Angular + .NET in parallel.
        gen_parallel = sfn.Parallel(
            self, "GenerateCode", result_path="$.generated",
        ).branch(gen_angular).branch(gen_dotnet)

        fail = sfn.Fail(self, "PipelineFailed", cause="A pipeline step failed")
        for t in (ingest_forms, ingest_plsql, analyse, gen_openapi,
                  validate, gen_tests, kb_sync):
            t.add_catch(fail, result_path="$.error")
        gen_parallel.add_catch(fail, result_path="$.error")

        definition = (
            ingest_forms
            .next(ingest_plsql)
            .next(analyse)
            .next(gen_openapi)
            .next(gen_parallel)
            .next(validate)
            .next(gen_tests)
            .next(kb_sync)
            .next(publish)
        )

        # STANDARD, not EXPRESS: Express state machines have a hard 5-minute
        # maximum duration (the `timeout` below is silently clamped to it). This
        # pipeline chains several Bedrock steps that use extended thinking
        # (analyse, generate, validate) and legitimately runs 6-10 minutes, so
        # Express timed out mid-run every time. STANDARD supports long-running
        # executions, gives full execution history + describe-execution, and
        # bills per state transition (~10/run) — negligible for this POC.
        # No explicit state_machine_name: a custom-named state machine cannot be
        # replaced in place (CloudFormation blocks it), and switching the type
        # forces a replacement. Letting CDK auto-generate the name lets CFN do a
        # clean create-new-then-delete-old. Consumers read the ARN from the
        # StateMachineArn output, not a hardcoded name.
        self.state_machine = sfn.StateMachine(
            self, "MigrationPipeline",
            state_machine_type=sfn.StateMachineType.STANDARD,
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(30),
            logs=sfn.LogOptions(destination=log_group, level=sfn.LogLevel.ALL),
        )

        CfnOutput(self, "StateMachineArn",
                  value=self.state_machine.state_machine_arn)
        CfnOutput(self, "SummaryTopicArn", value=self.topic.topic_arn)

    @staticmethod
    def _camel(snake: str) -> str:
        return "".join(p.capitalize() for p in snake.split("_"))
