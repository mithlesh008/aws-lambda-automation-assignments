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

<img width="895" height="519" alt="01" src="https://github.com/user-attachments/assets/b5d54b47-265b-4182-93ec-efb93bee922d" />

<img width="1611" height="554" alt="02" src="https://github.com/user-attachments/assets/9d699903-e640-4322-b983-fd27fe35dbd1" />

<img width="1611" height="632" alt="03" src="https://github.com/user-attachments/assets/9a85f753-5b74-47f2-9ae9-c168429b764d" />

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

<img width="1611" height="408" alt="04" src="https://github.com/user-attachments/assets/6ad94930-7596-4ce6-a4be-e07597e99995" />


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

<img width="1688" height="486" alt="05" src="https://github.com/user-attachments/assets/0f59332e-1c46-4700-9391-42cf60a388f3" />


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

<img width="924" height="224" alt="06" src="https://github.com/user-attachments/assets/968b1876-bbe2-422d-b80e-d38b50fc65ea" />


## 5. Test invocation and logs

For a manual console test, replace the instance ID in `test-event.json` with a running test instance ID. Then invoke:

```bash
sed "s/REPLACE_WITH_INSTANCE_ID/$INSTANCE_ID/" test-event.json >/tmp/test-event.json
aws lambda invoke --function-name ec2-auto-tag --payload fileb:///tmp/test-event.json --cli-binary-format raw-in-base64-out response.json
cat response.json
aws logs tail /aws/lambda/ec2-auto-tag --since 10m
```

<img width="888" height="447" alt="07" src="https://github.com/user-attachments/assets/85f57e65-ac02-4436-baa7-8cbb847fe476" />

<img width="1716" height="348" alt="08" src="https://github.com/user-attachments/assets/664408f5-45fd-4e3f-8f49-74f28ca8075c" />

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
