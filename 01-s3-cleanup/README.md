# Assignment 1: Automated S3 Bucket Cleanup

> **Beginner lab order:** First complete the root `README.md` Section 0 on the Amazon Linux instance. Then run `source ../lab.env` from this assignment directory before replacing the assignment variables below.


## Objective

Delete objects older than 30 days from one bucket or prefix. The test uses `AGE_SECONDS=60`; restore `AGE_SECONDS=2592000` before final submission or scheduling.

## 1. Create a test bucket and objects

```bash
export AWS_REGION=us-east-1
export BUCKET="lambda-cleanup-mbagga-$(date +%s)"
export PREFIX=test/
aws s3api create-bucket --bucket "$BUCKET" --region "$AWS_REGION"
printf 'old candidate\n' >/tmp/old.txt
printf 'new object\n' >/tmp/new.txt
aws s3 cp /tmp/old.txt "s3://$BUCKET/${PREFIX}old.txt"
sleep 70
aws s3 cp /tmp/new.txt "s3://$BUCKET/${PREFIX}new.txt"
aws s3api list-objects-v2 --bucket "$BUCKET" --prefix "$PREFIX" --query 'Contents[].{Key:Key,LastModified:LastModified}' --output table
```

[Screenshot 1: capture the initial S3 object listing before Lambda runs.]

## 2. Create the IAM role

Replace `REPLACE_BUCKET_NAME` and `REPLACE_PREFIX` in `inline-policy.json`. In the console: **IAM → Roles → Create role → AWS service → Lambda → Next → Create role**. Open the role, choose **Add permissions → Create inline policy → JSON**, paste the trust-independent permissions from `inline-policy.json`, and name it `S3CleanupPolicy`.

CLI alternative:

```bash
aws iam create-role --role-name S3CleanupLambdaRole --assume-role-policy-document file://trust-policy.json
aws iam put-role-policy --role-name S3CleanupLambdaRole --policy-name S3CleanupPolicy --policy-document file://inline-policy.json
export ROLE_ARN=$(aws iam get-role --role-name S3CleanupLambdaRole --query Role.Arn --output text)
```

[Screenshot 2: capture the role trust relationship and inline policy.]

## 3. Create and configure Lambda

```bash
cp lambda_function.py /tmp/lambda_function.py
sed "s#REPLACE#REPLACE#g" /dev/null >/dev/null  # no-op; source uses environment variables
zip function.zip lambda_function.py
aws lambda create-function \
  --function-name s3-old-object-cleaner \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role "$ROLE_ARN" \
  --zip-file fileb://function.zip \
  --timeout 60 \
  --environment "Variables={BUCKET=$BUCKET,PREFIX=$PREFIX,AGE_SECONDS=60}"
```

Console path: **Lambda → Create function → Author from scratch → Python 3.12 → Change default execution role → Use existing role → choose `S3CleanupLambdaRole` → Create function**. Upload `function.zip` under **Code → Upload from → .zip file**. Under **Runtime settings**, confirm handler `lambda_function.lambda_handler`. Under **Configuration → Environment variables**, add `BUCKET`, `PREFIX`, and `AGE_SECONDS=60`.

[Screenshot 3: capture runtime Python 3.12, handler, execution role, and environment variables.]

## 4. Test invocation

In the Lambda console select **Test**, create an event with `{}`, and invoke. Or use:

```bash
echo '{}' > test-event.json
aws lambda invoke --function-name s3-old-object-cleaner --payload fileb://test-event.json --cli-binary-format raw-in-base64-out response.json
cat response.json
aws s3api list-objects-v2 --bucket "$BUCKET" --prefix "$PREFIX" --query 'Contents[].Key' --output table
```

Only `new.txt` should remain. The function uses the paginator and batches deletes in groups of at most 1,000 objects.

[Screenshot 4: capture the Lambda test result showing `deleted_count` and deleted key names.]

## 5. CloudWatch logs

```bash
aws logs tail /aws/lambda/s3-old-object-cleaner --since 10m
```

[Screenshot 5: capture logs showing the bucket, cutoff, scanned count, and deleted object IDs/names.]

## 6. Restore the production setting

```bash
aws lambda update-function-configuration \
  --function-name s3-old-object-cleaner \
  --environment "Variables={BUCKET=$BUCKET,PREFIX=$PREFIX,AGE_SECONDS=2592000}"
```

Do this before enabling any schedule. For new automation, EventBridge Scheduler is preferred. If the assignment requires a scheduled EventBridge rule:

```bash
RULE_ARN=$(aws events put-rule --name s3-old-object-cleaner-daily --schedule-expression 'rate(1 day)' --state ENABLED --query RuleArn --output text)
FUNCTION_ARN=$(aws lambda get-function --function-name s3-old-object-cleaner --query Configuration.FunctionArn --output text)
aws events put-targets --rule s3-old-object-cleaner-daily --targets Id=cleanup,Arn="$FUNCTION_ARN"
aws lambda add-permission --function-name s3-old-object-cleaner --statement-id allow-eventbridge-cleanup --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn "$RULE_ARN"
```

[Screenshot 6: capture the enabled EventBridge rule, rate expression, and Lambda target if scheduling is demonstrated.]

## 7. Final result and cleanup

[Screenshot 7: capture the final S3 listing proving only newer objects remain.]

```bash
aws s3 rm "s3://$BUCKET/$PREFIX" --recursive
aws s3api delete-bucket --bucket "$BUCKET"
aws events remove-targets --rule s3-old-object-cleaner-daily --ids cleanup 2>/dev/null || true
aws events delete-rule --name s3-old-object-cleaner-daily 2>/dev/null || true
aws lambda remove-permission --function-name s3-old-object-cleaner --statement-id allow-eventbridge-cleanup 2>/dev/null || true
aws lambda delete-function --function-name s3-old-object-cleaner
aws iam delete-role-policy --role-name S3CleanupLambdaRole --policy-name S3CleanupPolicy
aws iam delete-role --role-name S3CleanupLambdaRole
rm -f function.zip response.json
```

## Discussion point

S3 Lifecycle Rules are the native choice for simple age-based expiration and avoid maintaining Lambda code. Lambda is justified when deletion depends on naming patterns, metadata, business conditions, cross-service actions, or notifications.
