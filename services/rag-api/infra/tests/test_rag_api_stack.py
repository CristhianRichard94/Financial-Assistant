"""CDK assertion tests for RagApiStack's Fargate HA configuration (issue #15).

These validate the synthesized CloudFormation template only - this stack has
not been deployed to real AWS, so there is no `cdk diff`/`cdk deploy`
verification here, only template-shape assertions via
`aws_cdk.assertions.Template`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

# Make the sibling `rag_api_stack.py` module importable when this test is run
# from anywhere (e.g. `pytest` invoked from the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_api_stack import MAX_TASK_COUNT, MIN_TASK_COUNT, RagApiStack  # noqa: E402


def _synth_template() -> Template:
    app = cdk.App()
    stack = RagApiStack(
        app,
        "TestRagApiStack",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


def test_desired_count_is_two() -> None:
    template = _synth_template()
    template.has_resource_properties(
        "AWS::ECS::Service",
        {"DesiredCount": MIN_TASK_COUNT},
    )
    assert MIN_TASK_COUNT == 2


def test_vpc_spans_at_least_two_azs() -> None:
    template = _synth_template()
    # Public subnets carry the task (see task_subnets= in the stack) - one
    # per AZ, so at least 2 subnets confirms at least 2 AZs are in use.
    subnets = template.find_resources("AWS::EC2::Subnet")
    assert len(subnets) >= 2

    def _az_key(az: object) -> object:
        # In some synth contexts (e.g. no `cdk.context.json` AZ lookup
        # cached), `AvailabilityZone` resolves to a literal string like
        # "dummy1a"/"dummy1b"; in others it's an unresolved
        # `{"Fn::Select": [i, {"Fn::GetAZs": ...}]}` token. Either way, a
        # distinct value per subnet means a distinct AZ.
        if isinstance(az, dict) and "Fn::Select" in az:
            return az["Fn::Select"][0]
        return az

    azs = {
        _az_key(props["Properties"]["AvailabilityZone"])
        for props in subnets.values()
    }
    assert len(azs) >= 2


def test_autoscaling_target_and_cpu_policy_exist() -> None:
    template = _synth_template()

    template.has_resource_properties(
        "AWS::ApplicationAutoScaling::ScalableTarget",
        {
            "MinCapacity": MIN_TASK_COUNT,
            "MaxCapacity": MAX_TASK_COUNT,
            "ServiceNamespace": "ecs",
            "ScalableDimension": "ecs:service:DesiredCount",
        },
    )

    template.has_resource_properties(
        "AWS::ApplicationAutoScaling::ScalingPolicy",
        {
            "PolicyType": "TargetTrackingScaling",
            "TargetTrackingScalingPolicyConfiguration": Match.object_like(
                {
                    "TargetValue": 60,
                    "PredefinedMetricSpecification": {
                        "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
                    },
                }
            ),
        },
    )
