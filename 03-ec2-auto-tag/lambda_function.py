import os
from datetime import datetime, timezone

import boto3

ec2 = boto3.client("ec2")


def lambda_handler(event, context):
    instance_id = event["detail"]["instance-id"]
    state = event["detail"].get("state", "unknown")
    details = ec2.describe_instances(InstanceIds=[instance_id])
    instance = details["Reservations"][0]["Instances"][0]

    launch_date = datetime.now(timezone.utc).date().isoformat()
    tags = [
        {"Key": "LaunchDate", "Value": launch_date},
        {"Key": os.environ.get("TAG_KEY", "Environment"),
         "Value": os.environ.get("TAG_VALUE", "Training")},
    ]
    ec2.create_tags(Resources=[instance_id], Tags=tags)
    result = {"instance_id": instance_id, "state": state,
              "instance_state": instance["State"]["Name"], "tags": tags}
    print(result)
    return result
