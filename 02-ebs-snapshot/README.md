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

## 2. Create the IAM role

```bash
aws iam create-role --role-name EbsSnapshotLambdaRole --assume-role-policy-document file://trust-policy.json
aws iam put-role-policy --role-name EbsSnapshotLambdaRole --policy-name EbsSnapshotPolicy --policy-document file://inline-policy.json
export ROLE_ARN=$(aws iam get-role --role-name EbsSnapshotLambdaRole --query Role.Arn --output text)
```

Console path: **IAM → Roles → Create role → Lambda → Create role → Add permissions → Create inline policy → JSON**. Paste `inline-policy.json` and name it `EbsSnapshotPolicy`. I have used CLI as shared above commands.

<img width="1601" height="574" alt="03" src="https://github.com/user-attachments/assets/2ff3a368-07cd-4508-8a08-74e9756c8932" />
<img width="794" height="655" alt="02" src="https://github.com/user-attachments/assets/f65d17e4-9cf2-4a68-92f8-caccfa500d7c" />



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

<img width="1006" height="502" alt="04" src="https://github.com/user-attachments/assets/0ae1bae3-948c-4ea9-a6e0-5bfb943d48dc" />


## 4. Test manually

```bash
aws lambda invoke --function-name ebs-snapshot-backup --payload fileb://test-event.json --cli-binary-format raw-in-base64-out q2-response.json
```
<img width="957" height="144" alt="05" src="https://github.com/user-attachments/assets/7b8975aa-14a1-4f3e-be7c-126dfdde2063" />

```bash
cat q2-response.json
```
<img width="957" height="165" alt="06" src="https://github.com/user-attachments/assets/e5fc7f27-db2a-4268-bb73-ae4644caaaf6" />


```bash
aws ec2 describe-snapshots --owner-ids self --filters Name=tag:CreatedBy,Values=Lambda-EBS-Backup --query 'Snapshots[].{Id:SnapshotId,State:State,StartTime:StartTime,Volume:VolumeId}' --output table
```
<img width="895" height="566" alt="08" src="https://github.com/user-attachments/assets/0ab7a445-27c1-4f0e-b8ad-7bcf60290b9f" />


`CreateSnapshot` is asynchronous, so the new snapshot may first show `pending`. Wait until it becomes `completed` before relying on it for restore.


## 5. Schedule weekly with EventBridge

The following legacy EventBridge scheduled rule runs Sundays at 03:00 UTC:

```bash
RULE_ARN=$(aws events put-rule --name <Name> --schedule-expression 'cron(0 3 ? * SUN *)' --state ENABLED --query RuleArn --output text)
FUNCTION_ARN=$(aws lambda get-function --function-name <Name> --query Configuration.FunctionArn --output text)
aws events put-targets --rule <Name> --targets Id=backup,Arn="$FUNCTION_ARN"
aws lambda add-permission --function-name <Name> --statement-id allow-ebs-weekly --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn "$RULE_ARN"
```

Console path: **Amazon EventBridge → Rules → Create rule → Schedule → cron expression → Target Lambda → ebs-snapshot-backup**. Scheduled expressions use UTC. EventBridge Scheduler may be used instead for a new deployment.

<img width="1711" height="328" alt="010" src="https://github.com/user-attachments/assets/7927a9b9-14ae-4e8f-8bec-a3c63e95e606" />

<img width="1711" height="220" alt="011" src="https://github.com/user-attachments/assets/f10e4961-2690-4a4a-8803-3459c18c0f59" />

## 6. CloudWatch logs and cleanup

```bash
aws logs tail /aws/lambda/ebs-snapshot-backup --since 1h
```
<img width="1711" height="328" alt="09" src="https://github.com/user-attachments/assets/9c9929c6-990e-4fb6-9395-8eadc24ef1bd" />

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
