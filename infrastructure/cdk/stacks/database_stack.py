"""DatabaseStack — Oracle Database XE 21c on an EC2 instance.

Runs Oracle via the gvenzl/oracle-xe community container image (the de-facto
standard for Oracle testing, e.g. Testcontainers) pulled from Docker Hub with no
login — so the POC needs no Oracle SSO credentials. RDS for Oracle is not an
option here: it is blocked in AWS dev/sandbox accounts (no Oracle engine in the RDS
catalog), because AWS does not extend License-Included Oracle to internal dev
accounts.

Host OS is Amazon Linux 2023 (the DB itself runs in the container, so the host
only needs Docker + a few CLI tools). Oracle Linux is not used: its AMIs are not
published under a public /aws/service SSM namespace, and the host OS is
immaterial when Oracle runs in a container.

UserData: install Docker, run the XE container (--restart=always), then load the
HR sample schema and the app_data schema packages downloaded from the
artifact bucket via the S3 gateway endpoint.

The instance sits in a private-with-egress subnet (no public IP, admin via SSM
Session Manager only). Egress via NAT is required to pull the image and clone
the HR sample schema; there is no inbound path from the internet.
"""
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
    aws_iam as iam,
)
from constructs import Construct


class DatabaseStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, prefix: str,
                 network, security, storage, **kwargs):
        super().__init__(scope, cid, **kwargs)
        self.prefix = prefix

        artifacts = storage.artifacts_bucket
        db_secret = security.oracle_secret

        # The instance role needs S3 read on the artifact bucket to pull the
        # loader SQL (input/) in UserData. Granted as an inline Policy created
        # HERE (not via artifacts.grant_read in SecurityStack): grant_read
        # would pull the StorageStack bucket ARN into SecurityStack and cycle
        # (StorageStack already depends on SecurityStack's KMS key). This stack
        # depends on both Storage and Security, so an inline Policy is
        # cycle-free. KMS decrypt is already granted on the role in
        # SecurityStack. Scoped to input/ — the only prefix UserData reads.
        iam.Policy(
            self, "OracleEc2ArtifactsReadPolicy",
            roles=[security.ec2_role],
            statements=[
                iam.PolicyStatement(
                    actions=["s3:GetObject"],
                    resources=[f"{artifacts.bucket_arn}/input/*"],
                ),
                iam.PolicyStatement(
                    actions=["s3:ListBucket"],
                    resources=[artifacts.bucket_arn],
                    conditions={"StringLike": {"s3:prefix": ["input/*"]}},
                ),
            ],
        )

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -euxo pipefail",
            # Amazon Linux 2023 uses dnf; git is needed for the HR sample clone.
            "dnf install -y docker jq git || yum install -y docker jq git",
            "systemctl enable --now docker",

            # Prepare the gp3 data volume for Oracle datafiles.
            "mkdir -p /opt/oracle/oradata",
            "if [ -b /dev/nvme1n1 ]; then DEV=/dev/nvme1n1; else DEV=/dev/sdb; fi",
            "if ! blkid $DEV; then mkfs -t xfs $DEV; fi",
            "mount $DEV /opt/oracle/oradata || true",
            "echo \"$DEV /opt/oracle/oradata xfs defaults,nofail 0 2\" >> /etc/fstab",
            # gvenzl image runs as uid 54321 (oracle); grant it ownership.
            "chown -R 54321:54321 /opt/oracle/oradata || chmod 777 /opt/oracle/oradata",

            f"REGION={Stack.of(self).region}",
            # DB password from the admin secret (drives ORACLE_PASSWORD for XE).
            f"DB_JSON=$(aws secretsmanager get-secret-value --region $REGION "
            f"--secret-id {db_secret.secret_name} --query SecretString --output text)",
            "DB_PWD=$(echo \"$DB_JSON\" | jq -r .password)",

            # Launch Oracle XE 21c via the gvenzl community image (Docker Hub, no
            # login). ORACLE_PASSWORD sets SYS/SYSTEM. Default PDB is XEPDB1.
            "docker run -d --name oraclexe --restart=always "
            "-p 1521:1521 "
            "-e ORACLE_PASSWORD=\"$DB_PWD\" "
            "-v /opt/oracle/oradata:/opt/oracle/oradata "
            "gvenzl/oracle-xe:21-slim",

            # Wait for the DB to be usable. The gvenzl image has NO docker
            # HEALTHCHECK; it signals readiness by printing 'DATABASE IS READY
            # TO USE!' to its logs. Poll the logs, then confirm with a real
            # sqlplus query against XEPDB1 (belt and suspenders).
            "for i in $(seq 1 80); do "
            "  if docker logs oraclexe 2>&1 | grep -q 'DATABASE IS READY TO USE'; then "
            "    echo 'oracle: log signals ready'; break; "
            "  fi; echo \"oracle: waiting ($i)\"; sleep 15; "
            "done",
            "for i in $(seq 1 40); do "
            "  if docker exec oraclexe bash -lc "
            "\"echo 'select 1 from dual;' | sqlplus -s system/$DB_PWD@localhost:1521/XEPDB1\" "
            "2>/dev/null | grep -q '1'; then echo 'oracle: query OK'; break; fi; "
            "  echo \"oracle: sqlplus not ready ($i)\"; sleep 15; "
            "done",

            # Pull the schema/PLSQL scripts from the artifact bucket.
            "mkdir -p /tmp/oracle-setup",
            f"aws s3 cp s3://{artifacts.bucket_name}/input/plsql-stubs/app_data_packages.sql "
            "/tmp/oracle-setup/ --region $REGION || true",
            f"aws s3 cp s3://{artifacts.bucket_name}/input/schema/load_hr_schema.sql "
            "/tmp/oracle-setup/ --region $REGION || true",

            # Install the Oracle sample HR schema.
            "cd /tmp/oracle-setup && git clone --depth 1 "
            "https://github.com/oracle/db-sample-schemas.git || true",

            # Run the loaders as SYSTEM against XEPDB1 inside the container.
            "docker cp /tmp/oracle-setup oraclexe:/tmp/oracle-setup || true",
            "docker exec oraclexe bash -lc "
            "\"cd /tmp/oracle-setup/db-sample-schemas/human_resources 2>/dev/null && "
            " echo @hr_install.sql | sqlplus -s system/$DB_PWD@localhost:1521/XEPDB1 || true\" || true",
            "docker exec oraclexe bash -lc "
            "\"sqlplus -s system/$DB_PWD@localhost:1521/XEPDB1 @/tmp/oracle-setup/load_hr_schema.sql || true\"",
            "docker exec oraclexe bash -lc "
            "\"sqlplus -s system/$DB_PWD@localhost:1521/XEPDB1 @/tmp/oracle-setup/app_data_packages.sql || true\"",

            # The SQL creates APP_DATA with a placeholder password. Align it with
            # the generated secret so the ECS task (user app_data) can log in.
            # Written to a file so the password (which may contain shell/SQL
            # metacharacters) is quoted once, cleanly, rather than escaped through
            # nested docker/sqlplus quoting.
            "printf 'ALTER USER app_data IDENTIFIED BY \"%s\";\\n' \"$DB_PWD\""
            "> /tmp/oracle-setup/align_pwd.sql",
            "docker cp /tmp/oracle-setup/align_pwd.sql oraclexe:/tmp/align_pwd.sql",
            "docker exec oraclexe bash -lc "
            "\"sqlplus -s system/$DB_PWD@localhost:1521/XEPDB1 @/tmp/align_pwd.sql\"",

            "echo 'Oracle bootstrap complete' > /var/log/oracle-bootstrap.done",
        )

        # Amazon Linux 2023 (x86_64) via the AWS-maintained SSM parameter.
        # awscli v2 is preinstalled; Docker + git are added in UserData.
        machine_image = ec2.MachineImage.latest_amazon_linux2023(
            cpu_type=ec2.AmazonLinuxCpuType.X86_64)

        self.instance = ec2.Instance(
            self, "OracleInstance",
            instance_name=f"{prefix}-oracle",
            vpc=network.vpc,
            # Private-with-egress (not isolated): the container image pull and HR
            # schema git clone need outbound internet via NAT. Still no public IP;
            # inbound is limited to 1521 from the app/pipeline SGs.
            vpc_subnets=network.private_subnets,
            security_group=network.oracle_sg,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.LARGE),
            machine_image=machine_image,
            role=security.ec2_role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",  # AL2023 root device
                    volume=ec2.BlockDeviceVolume.ebs(
                        30, volume_type=ec2.EbsDeviceVolumeType.GP3)),
                ec2.BlockDevice(
                    device_name="/dev/sdb",   # Oracle data
                    volume=ec2.BlockDeviceVolume.ebs(
                        50, volume_type=ec2.EbsDeviceVolumeType.GP3)),
            ],
        )

        self.private_ip = self.instance.instance_private_ip

        CfnOutput(self, "OracleInstanceId", value=self.instance.instance_id)
        CfnOutput(self, "OraclePrivateIp", value=self.private_ip)
        CfnOutput(self, "OracleConnectHint",
                  value=f"aws ssm start-session --target {self.instance.instance_id}")
