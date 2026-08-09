import os
from datetime import datetime, timedelta, timezone

import boto3

ec2 = boto3.client("ec2")
CREATED_BY = os.environ.get("CREATED_BY", "Lambda-Backup")


def lambda_handler(event, context):
    volume_id = os.environ["VOLUME_ID"]
    retention_days = int(os.environ.get("RETENTION_DAYS", "30"))

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)

    print(f"Source volume: {volume_id}")
    print(f"Retention days: {retention_days}")
    print(f"Current UTC time: {now.isoformat()}")
    print(f"Snapshot cutoff time: {cutoff.isoformat()}")

    create_response = ec2.create_snapshot(
        VolumeId=volume_id,
        Description=f"Lambda backup of EBS volume {volume_id}",
    )

    created_snapshot_id = create_response["SnapshotId"]

    ec2.create_tags(
        Resources=[created_snapshot_id],
        Tags=[
            {"Key": "CreatedBy", "Value": CREATED_BY},
            {"Key": "SourceVolumeId", "Value": volume_id},
            {"Key": "BackupType", "Value": "Automated-EBS"},
            {"Key": "CreatedDate", "Value": now.strftime("%Y-%m-%d")},
        ],
    )

    print(f"Created snapshot: {created_snapshot_id}")

    deleted_snapshot_ids = []
    delete_errors = []

    paginator = ec2.get_paginator("describe_snapshots")
    pages = paginator.paginate(
        OwnerIds=["self"],
        Filters=[
            {"Name": "tag:CreatedBy", "Values": [CREATED_BY]},
            {"Name": "tag:SourceVolumeId", "Values": [volume_id]},
        ],
    )

    for page in pages:
        for snapshot in page.get("Snapshots", []):
            snapshot_id = snapshot["SnapshotId"]
            start_time = snapshot["StartTime"]

            # Never delete the snapshot created by this invocation.
            if snapshot_id == created_snapshot_id:
                continue

            if start_time < cutoff:
                try:
                    ec2.delete_snapshot(SnapshotId=snapshot_id)
                    deleted_snapshot_ids.append(snapshot_id)
                    print(f"Deleted old snapshot: {snapshot_id}")
                except Exception as error:
                    error_message = f"{snapshot_id}: {error}"
                    delete_errors.append(error_message)
                    print(f"Snapshot deletion failed: {error_message}")

    result = {
        "volume_id": volume_id,
        "created_snapshot_id": created_snapshot_id,
        "retention_days": retention_days,
        "deleted_snapshot_ids": deleted_snapshot_ids,
        "delete_errors": delete_errors,
    }

    print(f"Final result: {result}")
    return result
