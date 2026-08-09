import json
import os
from datetime import datetime, timedelta, timezone

import boto3

s3 = boto3.client("s3")

BUCKET = os.environ["BUCKET"]
PREFIX = os.environ.get("PREFIX", "")
AGE_SECONDS = int(os.environ.get("AGE_SECONDS", "2592000"))

def log(message):
    print(json.dumps(message, default=str))

def lambda_handler(event, context):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=AGE_SECONDS)

    scanned = 0
    candidates = []
    deleted_keys = []
    errors = []

    log({
        "event": "cleanup_started",
        "bucket": BUCKET,
        "prefix": PREFIX,
        "age_seconds": AGE_SECONDS,
        "current_time": now.isoformat(),
        "cutoff": cutoff.isoformat(),
    })

    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(
        Bucket=BUCKET,
        Prefix=PREFIX,
    ):
        for obj in page.get("Contents", []):
            scanned += 1

            key = obj["Key"]
            last_modified = obj["LastModified"]
            is_old = last_modified < cutoff

            log({
                "event": "object_checked",
                "key": key,
                "last_modified": last_modified.isoformat(),
                "cutoff": cutoff.isoformat(),
                "is_old": is_old,
            })

            if is_old:
                candidates.append({
                    "Key": key
                })

    log({
        "event": "deletion_candidates_found",
        "candidate_count": len(candidates),
        "candidate_keys": [item["Key"] for item in candidates],
    })

    # S3 DeleteObjects supports a maximum of 1,000 objects per request.
    for start in range(0, len(candidates), 1000):
        batch = candidates[start:start + 1000]

        if not batch:
            continue

        # Do not use Quiet=True.
        # Quiet=False allows S3 to return successfully deleted objects.
        response = s3.delete_objects(
            Bucket=BUCKET,
            Delete={
                "Objects": batch,
                "Quiet": False,
            },
        )

        for item in response.get("Deleted", []):
            key = item["Key"]
            deleted_keys.append(key)

            log({
                "event": "object_deleted",
                "key": key,
            })

        for error in response.get("Errors", []):
            errors.append(error)

            log({
                "event": "delete_error",
                "error": error,
            })

    if errors:
        log({
            "event": "cleanup_failed",
            "errors": errors,
        })
        raise RuntimeError(f"S3 deletion errors: {errors}")

    result = {
        "event": "cleanup_completed",
        "bucket": BUCKET,
        "prefix": PREFIX,
        "age_seconds": AGE_SECONDS,
        "cutoff": cutoff.isoformat(),
        "scanned": scanned,
        "candidate_count": len(candidates),
        "deleted_count": len(deleted_keys),
        "deleted_keys": deleted_keys,
    }

    log(result)

    return result

