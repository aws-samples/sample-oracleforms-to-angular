"""ObservabilityStack — CloudWatch dashboard + VPC flow logs (lightweight).

Kept optional and cheap: a single dashboard summarising the pipeline state
machine and the .NET API service, plus VPC flow logs for auditability. CloudTrail
is assumed to be on at the account level, so it is not duplicated here.
"""
from aws_cdk import (
    Stack,
    aws_cloudwatch as cw,
)
from constructs import Construct


class ObservabilityStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, prefix: str,
                 pipeline, api, **kwargs):
        super().__init__(scope, cid, **kwargs)

        # Referencing the pipeline state machine's metrics imports its ARN via a
        # CloudFormation cross-stack export, which pins the machine: it cannot be
        # replaced while this stack holds the import. Replacing the machine
        # (e.g. EXPRESS->STANDARD) therefore needs a 3-pass deploy — detach here,
        # replace the machine, reattach. Set context -c detach_pipeline_metric=1
        # to drop the import for the detach pass.
        detach = self.node.try_get_context("detach_pipeline_metric")

        # VPC flow logs are owned by NetworkStack (add_flow_log mutates the VPC,
        # which would cycle if done here). This stack is dashboards only.
        dashboard = cw.Dashboard(
            self, "Dashboard", dashboard_name=f"{prefix}-dashboard")

        widgets = []
        # Omit the whole pipeline widget when detached — an empty-metric widget
        # is a CloudWatch validation error, so we drop the widget, not its data.
        if not detach:
            widgets.append(cw.GraphWidget(
                title="Migration pipeline executions",
                left=[
                    pipeline.state_machine.metric_succeeded(),
                    pipeline.state_machine.metric_failed(),
                ],
                width=12,
            ))
        widgets.append(cw.GraphWidget(
            title=".NET API — CPU / Memory",
            left=[
                api.service.service.metric_cpu_utilization(),
                api.service.service.metric_memory_utilization(),
            ],
            width=12,
        ))
        dashboard.add_widgets(*widgets)
