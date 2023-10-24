from aws_cdk import (
    Stack,
    Duration,
    BundlingOptions,
    aws_ec2 as ec2,
    aws_autoscaling as autoscaling,
    aws_secretsmanager as secretsmanager,
    aws_lambda as lambda_,
    aws_iam as iam,
)
from constructs import Construct
import os
import inspect


class TypesenseAutoScalingStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, 
        vpc,
        availability_zone,
        typesense_ebs_volume,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        region = "us-east-1"
        volume_device = "/dev/sdi"
        volume_mount_path = "/mnt/ebs"
        port = 8108
        version = "0.25.0"

        ########################
        # Typesense Elastic IP #
        ########################
        elastic_ip = ec2.CfnEIP(self, "TypesenseEC2ElasticIP",
            tags=[{"key":"Name", "value":"TypesenseEC2ElasticIP"}],
        )

        ##############################
        # Typesense Boostrap API Key #
        ##############################
        typesense_bootstrap_api_key = secretsmanager.Secret(self, "TypesenseBootstrapAPIKeySecret",
            secret_name="TypesenseBootstrapAPIKey",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_uppercase=True,
                exclude_punctuation=True,
                password_length=64,    
            ),
        )

        #############################
        # Typesense EC2 AutoScaling #
        #############################
        typesense_ec2_role = iam.Role(self, "TypesenseEC2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            role_name="TypesenseEC2",
            description='Role for Typesense EC2 instance to be able to associate the existing elastic ip and attach the existing EBS volume upon an autoscale activity.', 
            inline_policies={
                'typesense_ec2': iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ec2:AttachVolume",
                                "ec2:DescribeVolumes",
                                "ec2:AssociateAddress",
                            ],
                            resources=["*"],
                        ),
                    ]
                ),
                'secretsmanager_read': iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "secretsmanager:GetSecretValue",
                            ],
                            resources=["*"],
                        ),
                    ]
                ),
            },
        )

        typesense_autoscaling_user_data_path = os.path.abspath(os.path.join(os.getcwd(), "typesense_ec2", "install_script.sh"))
        user_data = ec2.UserData.for_linux()
        # TODO: make the python vars embedded in this script all be at the top, defined as bash vars in this script.
        user_data.add_commands(inspect.cleandoc(
            f"""
            # get jq
            sudo yum install jq

            # get instance-id
            TOKEN=$(curl -X PUT -H "X-aws-ec2-metadata-token-ttl-seconds: 600" "http://instance-data/latest/api/token")
            EC2_INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://instance-data/latest/meta-data/instance-id)

            # associate the Elastic IP address to the instance
            aws ec2 associate-address --instance-id $EC2_INSTANCE_ID --allocation-id {elastic_ip.attr_allocation_id} --allow-reassociation  --region {region}

            # attach volume
            aws ec2 attach-volume --device {volume_device} --instance-id $EC2_INSTANCE_ID --volume-id {typesense_ebs_volume.volume_id} --region {region}

            # wait for volume to be properly attached
            DATA_STATE="unknown"
            until [ "${{!DATA_STATE}}" == "attached" ]; do
                DATA_STATE=$(aws ec2 describe-volumes \
                    --region {region} \
                    --filters \
                        Name=attachment.instance-id,Values=${{!EC2_INSTANCE_ID}} \
                        Name=attachment.device,Values={volume_device} \
                    --query Volumes[].Attachments[].State \
                    --output text)

                sleep 5
            done

            # format the volume if doesn't have file system
            blkid --match-token TYPE=ext4 {volume_device} || mkfs.ext4 -m0 {volume_device}

            # create mount root folder
            mkdir -p {volume_mount_path}

            # mount the volume to folder
            mount {volume_device} {volume_mount_path}

            # persist the volume on restart
            echo "{volume_device} {volume_mount_path} ext4 defaults,nofail 0 2" >> /etc/fstab

            # get the api key for bootstrapping typesense
            secretsmanager_resp=$(aws secretsmanager get-secret-value \
                --secret-id {typesense_bootstrap_api_key.secret_name})
            ApiKey=$(echo $secretsmanager_resp | jq -r .SecretString)

            # create typesense server config
            if [ ! -f {volume_mount_path}/typesense.ini ]
            then
                echo "[server]
            api-key = ${{ApiKey}}
            data-dir = {volume_mount_path}/data
            log-dir = {volume_mount_path}/log
            api-port = {port}" > {volume_mount_path}/typesense.ini
                chown ec2-user:ec2-user {volume_mount_path}/typesense.ini
            fi

            # create typesense data folder if not exists
            if [ ! -d {volume_mount_path}/data ]
            then
                mkdir -p {volume_mount_path}/data
                chown ec2-user:ec2-user {volume_mount_path}/data
            fi

            # create typesense logs folder if not exists
            if [ ! -d {volume_mount_path}/log ]
            then
                mkdir -p {volume_mount_path}/log
                chown ec2-user:ec2-user {volume_mount_path}/log
            fi

            # download & unarchive typesense
            curl -O https://dl.typesense.org/releases/{version}/typesense-server-{version}-linux-arm64.tar.gz
            tar -xzf typesense-server-{version}-linux-arm64.tar.gz -C /home/ec2-user
            # remove archive
            rm typesense-server-{version}-linux-arm64.tar.gz

            # create typesense service
            echo "[Unit]
            Description=Typesense service
            After=network.target

            [Service]
            Type=simple
            Restart=always
            RestartSec=5
            User=ec2-user
            ExecStart=/home/ec2-user/typesense-server --config={volume_mount_path}/typesense.ini

            [Install]
            WantedBy=default.target" > /etc/systemd/system/typesense.service

            # start typesense service
            systemctl start typesense
            # enable typesense daemon
            systemctl enable typesense
            """
        ))
        autoscaling_group = autoscaling.AutoScalingGroup(self, "TypesenseAutoScalingGroup",
            auto_scaling_group_name="Typesense",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                availability_zones=[availability_zone],
            ),
            role=typesense_ec2_role,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, 
                ec2.InstanceSize.SMALL,
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64,
            ),
            desired_capacity=1,
            min_capacity=0,
            user_data=user_data,
            ssm_session_permissions=True,
        )
        autoscaling_group.connections.allow_from_any_ipv4(ec2.Port.tcp(port), "Allow inbound HTTP")

        ##################################
        # Lambda for Generating API Keys #
        ##################################
        generate_typesense_keys_lambda_role = iam.Role(self, "GenerateTypesenseApiKeysLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            role_name="GenerateTypesenseApiKeysLambdaRole",
            description='Role for the lambda that reaches out to Typesense to generate api keys.',
            inline_policies={
                'secrets_manager_read_create_update': iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "secretsmanager:GetSecretValue",
                                "secretsmanager:CreateSecret",
                                "secretsmanager:UpdateSecret",
                            ],
                            resources=["*"],
                        ),
                    ]
                ),
            },
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        typesense_lambda_source_dir = os.path.join(os.path.dirname(__file__), '..', "lambdas", "typesense_api_keys_lambda")
        generate_typsense_keys_lambda_function = lambda_.Function(self, "GenerateTypesenseApiKeysLambdaFunction",
            function_name="GenerateTypesenseApiKeys",
            role=generate_typesense_keys_lambda_role,
            runtime=lambda_.Runtime.PYTHON_3_10,
            timeout=Duration.seconds(60),
            handler="typesense_api_keys_handler.lambda_handler",
            code=lambda_.Code.from_asset(
                typesense_lambda_source_dir,
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_10.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --no-cache -r requirements.txt -t /asset-output && cp -au . /asset-output"
                    ],
                ),
            ),
            environment={
                "TYPESENSE_ELASTIC_IP": elastic_ip.attr_public_ip,
                "TYPESENSE_PORT": str(port),
            },
        )