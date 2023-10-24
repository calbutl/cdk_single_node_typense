from aws_cdk import (
    Stack,
    Size,
    RemovalPolicy,
    aws_ec2 as ec2,
)
from constructs import Construct


class TypesenseEBSVolumeStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, 
        availability_zone,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        
        ########################
        # Typesense EBS Volume #
        ########################
        typesense_ebs_volume = ec2.Volume(self, "TypesenseEBSVolume", 
            availability_zone=availability_zone, 
            removal_policy=RemovalPolicy.SNAPSHOT, 
            size=Size.gibibytes(2), 
            volume_name="TypesenseEBSVolume", 
            volume_type=ec2.EbsDeviceVolumeType.GP3,
        )

        self.typesense_ebs_volume = typesense_ebs_volume