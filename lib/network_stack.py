from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
)
from constructs import Construct


class NetworkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, 
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        default_vpc = ec2.Vpc.from_lookup(self, "DefaultVPC", is_default=True)
        az = default_vpc.availability_zones[0]

        self.vpc = default_vpc
        self.availability_zone = az
