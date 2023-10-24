#!/usr/bin/env python3
import os

import aws_cdk as cdk

from lib.network_stack import NetworkStack
from lib.typesense_ebs_volume_stack import TypesenseEBSVolumeStack
from lib.typesense_auto_scaling_stack import TypesenseAutoScalingStack


app = cdk.App()

env = cdk.Environment(      
    account=os.environ.get("CDK_DEPLOY_ACCOUNT", os.environ["CDK_DEFAULT_ACCOUNT"]),
    region=os.environ.get("CDK_DEPLOY_REGION", os.environ["CDK_DEFAULT_REGION"])
)

network_stack = NetworkStack(app, "NetworkStack",
    env=env,
)

typesense_ebs_volume_stack = TypesenseEBSVolumeStack(app, "TypesenseEBSVolumeStack",
    env=env,
    availability_zone=network_stack.availability_zone,
)

typesense_autoscaling_stack = TypesenseAutoScalingStack(app, "TypesenseAutoScalingStack",
    env=env,
    vpc=network_stack.vpc,
    availability_zone=network_stack.availability_zone,
    typesense_ebs_volume=typesense_ebs_volume_stack.typesense_ebs_volume,
)

app.synth()
