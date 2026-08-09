import os
import time
from datetime import datetime, timezone

import boto3

ec2 = boto3.client("ec2")
SOURCE_VOLUME_ID = os.environ["SOURCE_VOLUME_ID"]
SUBNET_ID = os.environ["SUBNET_ID"]
SECURITY_GROUP_ID = os.environ["SECURITY_GROUP_ID"]
KEY_NAME = os.environ.get("KEY_NAME", "")
ROOT_DEVICE_NAME = os.environ.get("ROOT_DEVICE_NAME", "/dev/xvda")
INSTANCE_TYPE = os.environ.get("INSTANCE_TYPE", "t3.micro")


def latest_snapshot():
    response = ec2.describe_snapshots(
        OwnerIds=["self"],
        Filters=[
            {"Name": "volume-id", "Values": [SOURCE_VOLUME_ID]},
            {"Name": "status", "Values": ["completed"]},
        ],
    )
    snapshots = response.get("Snapshots", [])
    if not snapshots:
        raise RuntimeError(f"No completed snapshot found for {SOURCE_VOLUME_ID}")
    return max(snapshots, key=lambda item: item["StartTime"])


def lambda_handler(event, context):
    snapshot = latest_snapshot()
    snapshot_id = snapshot["SnapshotId"]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ami_name = f"lambda-restore-{timestamp}"

    image_id = ec2.register_image(
        Name=ami_name,
        Description=f"Restored from {snapshot_id}",
        Architecture="x86_64",
        VirtualizationType="hvm",
        RootDeviceName=ROOT_DEVICE_NAME,
        BlockDeviceMappings=[{
            "DeviceName": ROOT_DEVICE_NAME,
            "Ebs": {"SnapshotId": snapshot_id, "DeleteOnTermination": True},
        }],
        TagSpecifications=[{
            "ResourceType": "image",
            "Tags": [
                {"Key": "RestoredFrom", "Value": snapshot_id},
                {"Key": "ManagedBy", "Value": "Lambda-EC2-Restore"},
            ],
        }],
    )["ImageId"]
    print(f"Registered AMI {image_id} from snapshot {snapshot_id}")

    waiter = ec2.get_waiter("image_available")
    waiter.wait(ImageIds=[image_id], WaiterConfig={"Delay": 10, "MaxAttempts": 60})

    request = {
        "ImageId": image_id,
        "InstanceType": INSTANCE_TYPE,
        "MinCount": 1,
        "MaxCount": 1,
        "SubnetId": SUBNET_ID,
        "SecurityGroupIds": [SECURITY_GROUP_ID],
        "TagSpecifications": [{
            "ResourceType": "instance",
            "Tags": [
                {"Key": "RestoredFrom", "Value": snapshot_id},
                {"Key": "ManagedBy", "Value": "Lambda-EC2-Restore"},
            ],
        }],
    }
    if KEY_NAME:
        request["KeyName"] = KEY_NAME

    instance_id = ec2.run_instances(**request)["Instances"][0]["InstanceId"]
    print(f"Launched restored instance {instance_id}")
    return {"snapshot_id": snapshot_id, "image_id": image_id, "instance_id": instance_id}
