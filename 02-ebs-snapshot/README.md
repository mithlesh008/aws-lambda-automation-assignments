# Assignment 2: Automated EBS Snapshot Creation and Cleanup

> **Beginner lab order:** First complete the root `README.md` Section 0 on the Amazon Linux instance. Then run `source ../lab.env` from this assignment directory before replacing the assignment variables below.


## Objective

Create a snapshot for one or more EBS volumes, tag it, and delete snapshots with the Lambda tag older than 30 days.

## 1. Identify a test volume

```bash
aws ec2 describe-volumes --filters Name=status,Values=available,in-use --query 'Volumes[].{VolumeId:VolumeId,State:State,Size:Size,Tags:Tags}' --output table
export VOLUME_ID=REPLACE_WITH_VOLUME_ID
```

Use a disposable volume or a nonproduction volume. Note the Region because snapshots are Regional.

[Screenshot 1: capture the volume ID and status in the EC2 console.]

## 2. Create the IAM role

```bash
aws iam create-role --role-name EbsSnapshotLambdaRole --assume-role-policy-document file://trust-policy.json
aws iam put-role-policy --role-name EbsSnapshotLambdaRole --policy-name EbsSnapshotPolicy --policy-document file://inline-policy.json
export ROLE_ARN=$(aws iam get-role --role-name EbsSnapshotLambdaRole --query Role.Arn --output text)
```

Console path: **IAM → Roles → Create role → Lambda → Create role → Add permissions → Create inline policy → JSON**. Paste `inline-policy.json` and name it `EbsSnapshotPolicy`.

[Screenshot 2: capture the IAM role trust relationship and inline policy.]

## 3. Package and create Lambda

```bash
zip function.zip lambda_function.py
aws lambda create-function \
  --function-name ebs-snapshot-backup \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role "$ROLE_ARN" \
  --zip-file fileb://function.zip \
  --timeout 60 \
  --environment "Variables={VOLUME_IDS=$VOLUME_ID,RETENTION_DAYS=30,MANAGED_BY=Lambda-EBS-Backup}"
```

Console: create Python 3.12 function, upload the ZIP, confirm handler `lambda_function.lambda_handler`, then add `VOLUME_IDS`, `RETENTION_DAYS=30`, and `MANAGED_BY` environment variables.

[Screenshot 3: capture Lambda runtime, handler, role, and environment variables.]

## 4. Test manually

```bash
aws lambda invoke --function-name ebs-snapshot-backup --payload fileb://test-event.json --cli-binary-format raw-in-base64-out response.json
cat response.json
aws ec2 describe-snapshots --owner-ids self --filters Name=tag:CreatedBy,Values=Lambda-EBS-Backup --query 'Snapshots[].{Id:SnapshotId,State:State,StartTime:StartTime,Volume:VolumeId}' --output table
```

`CreateSnapshot` is asynchronous, so the new snapshot may first show `pending`. Wait until it becomes `completed` before relying on it for restore.

[Screenshot 4: capture the Lambda invocation result and created snapshot ID.]

## 5. Test cleanup logic safely

Do not delete a real snapshot solely for the assignment. For a controlled test, temporarily set `RETENTION_DAYS=0`, invoke once, and verify the behavior only against snapshots carrying `CreatedBy=Lambda-EBS-Backup`. Restore `RETENTION_DAYS=30` immediately afterward.

[Screenshot 5: capture the EC2 Snapshots console filtered by the `CreatedBy` tag and the created/deleted IDs.]

## 6. Schedule weekly with EventBridge

The following legacy EventBridge scheduled rule runs Sundays at 03:00 UTC:

```bash
RULE_ARN=$(aws events put-rule --name ebs-snapshot-weekly --schedule-expression 'cron(0 3 ? * SUN *)' --state ENABLED --query RuleArn --output text)
FUNCTION_ARN=$(aws lambda get-function --function-name ebs-snapshot-backup --query Configuration.FunctionArn --output text)
aws events put-targets --rule ebs-snapshot-weekly --targets Id=backup,Arn="$FUNCTION_ARN"
aws lambda add-permission --function-name ebs-snapshot-backup --statement-id allow-ebs-weekly --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn "$RULE_ARN"
```

Console path: **Amazon EventBridge → Rules → Create rule → Schedule → cron expression → Target Lambda → ebs-snapshot-backup**. Scheduled expressions use UTC. EventBridge Scheduler may be used instead for a new deployment.

[Screenshot 6: capture the enabled weekly schedule and Lambda target.]

## 7. CloudWatch logs and cleanup

```bash
aws logs tail /aws/lambda/ebs-snapshot-backup --since 1h
```

[Screenshot 7: capture logs showing created and deleted snapshot IDs.]

After screenshots:

```bash
aws events remove-targets --rule ebs-snapshot-weekly --ids backup 2>/dev/null || true
aws events delete-rule --name ebs-snapshot-weekly 2>/dev/null || true
aws lambda remove-permission --function-name ebs-snapshot-backup --statement-id allow-ebs-weekly 2>/dev/null || true
aws lambda delete-function --function-name ebs-snapshot-backup
aws iam delete-role-policy --role-name EbsSnapshotLambdaRole --policy-name EbsSnapshotPolicy
aws iam delete-role --role-name EbsSnapshotLambdaRole
aws ec2 describe-snapshots --owner-ids self --filters Name=tag:CreatedBy,Values=Lambda-EBS-Backup --query 'Snapshots[].SnapshotId' --output text
# Delete only confirmed disposable IDs:
# aws ec2 delete-snapshot --snapshot-id snap-0123456789abcdef0
rm -f function.zip response.json
```

## Discussion point

AWS Data Lifecycle Manager is the preferred managed service for standard EBS snapshot schedules and retention policies because it reduces custom code and operational maintenance. Lambda is more appropriate when backup logic requires custom retention rules, cross-account or cross-Region copies, conditional processing, tagging workflows, or notifications to external systems.
