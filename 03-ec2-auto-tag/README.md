# Assignment 3: Auto-Tagging EC2 Instances on Launch

> **Beginner lab order:** First complete the root `README.md` Section 0 on the Amazon Linux instance. Then run `source ../lab.env` from this assignment directory before replacing the assignment variables below.


## Objective

When an EC2 instance reaches `running`, EventBridge invokes Lambda. Lambda tags it with `LaunchDate` and a custom tag.

## 1. Create the IAM role

```bash
aws iam create-role --role-name Ec2AutoTagLambdaRole --assume-role-policy-document file://trust-policy.json
aws iam put-role-policy --role-name Ec2AutoTagLambdaRole --policy-name Ec2AutoTagPolicy --policy-document file://inline-policy.json
export ROLE_ARN=$(aws iam get-role --role-name Ec2AutoTagLambdaRole --query Role.Arn --output text)
```

Console: **IAM → Roles → Create role → Lambda**. Add `inline-policy.json` as an inline policy named `Ec2AutoTagPolicy`.

[Screenshot 1: capture the IAM role trust relationship and inline policy.]

## 2. Create Lambda

```bash
zip function.zip lambda_function.py
aws lambda create-function \
  --function-name ec2-auto-tag \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role "$ROLE_ARN" \
  --zip-file fileb://function.zip \
  --timeout 15 \
  --environment 'Variables={TAG_KEY=Environment,TAG_VALUE=Training}'
```

Console: create Python 3.12 function, upload the ZIP, confirm handler, and add `TAG_KEY=Environment` and `TAG_VALUE=Training`.

[Screenshot 2: capture Lambda configuration.]

## 3. Create the EventBridge event pattern

```bash
cat > pattern.json <<'JSON'
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Instance State-change Notification"],
  "detail": {"state": ["running"]}
}
JSON

RULE_ARN=$(aws events put-rule --name ec2-auto-tag-on-running --event-pattern file://pattern.json --state ENABLED --query RuleArn --output text)
FUNCTION_ARN=$(aws lambda get-function --function-name ec2-auto-tag --query Configuration.FunctionArn --output text)
aws events put-targets --rule ec2-auto-tag-on-running --targets Id=auto-tag,Arn="$FUNCTION_ARN"
aws lambda add-permission --function-name ec2-auto-tag --statement-id allow-ec2-auto-tag --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn "$RULE_ARN" --source-account "$ACCOUNT_ID"
```

Console path: **Amazon EventBridge → Rules → Create rule → Event pattern → Custom pattern**. Paste `pattern.json`, select the Lambda target, and create the rule.

[Screenshot 3: capture the rule event pattern, enabled state, and Lambda target.]

## 4. Test with a disposable t3.micro

Use an existing AMI, subnet, security group, and key pair. Do not expose SSH to the world.

```bash
export AMI_ID=ami-xxxxxxxxxxxxxxxxx
export SUBNET_ID=subnet-xxxxxxxxxxxxxxxxx
export SECURITY_GROUP_ID=sg-xxxxxxxxxxxxxxxxx
export KEY_NAME=your-key-pair
INSTANCE_ID=$(aws ec2 run-instances --image-id "$AMI_ID" --instance-type t3.micro --count 1 --subnet-id "$SUBNET_ID" --security-group-ids "$SECURITY_GROUP_ID" --key-name "$KEY_NAME" --tag-specifications 'ResourceType=instance,Tags=[{Key=Purpose,Value=auto-tag-test}]' --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
aws ec2 describe-tags --filters Name=resource-id,Values="$INSTANCE_ID" --output table
```

The event may take a short time to arrive. EventBridge events are best-effort and the Lambda tagging operation is idempotent for the same tag keys.

[Screenshot 4: capture `LaunchDate` and `Environment=Training` on the instance.]

## 5. Test invocation and logs

For a manual console test, replace the instance ID in `test-event.json` with a running test instance ID. Then invoke:

```bash
sed "s/REPLACE_WITH_INSTANCE_ID/$INSTANCE_ID/" test-event.json >/tmp/test-event.json
aws lambda invoke --function-name ec2-auto-tag --payload fileb:///tmp/test-event.json --cli-binary-format raw-in-base64-out response.json
cat response.json
aws logs tail /aws/lambda/ec2-auto-tag --since 10m
```

[Screenshot 5: capture the test output.]

[Screenshot 6: capture CloudWatch logs showing the instance ID and tags.]

## Optional bonus: CloudTrail owner tag

The EC2 state-change event does not contain the launching IAM principal. A bonus implementation can add `cloudtrail:LookupEvents`, search for `RunInstances` shortly before the state event, match the instance ID, and set an `Owner` tag to `userIdentity.arn`. This is eventual and can be ambiguous for Auto Scaling, assumed roles, or service launches; document the limitation.

## Cleanup

```bash
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID"
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
aws events remove-targets --rule ec2-auto-tag-on-running --ids auto-tag 2>/dev/null || true
aws events delete-rule --name ec2-auto-tag-on-running 2>/dev/null || true
aws lambda remove-permission --function-name ec2-auto-tag --statement-id allow-ec2-auto-tag 2>/dev/null || true
aws lambda delete-function --function-name ec2-auto-tag
aws iam delete-role-policy --role-name Ec2AutoTagLambdaRole --policy-name Ec2AutoTagPolicy
aws iam delete-role --role-name Ec2AutoTagLambdaRole
rm -f function.zip pattern.json response.json
```

## Final result screenshot

[Screenshot 7: capture the final EC2 instance tags and the Lambda log result before cleanup.]
