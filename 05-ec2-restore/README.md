# Assignment 5: Restore an EC2 Instance from the Latest Snapshot

> **Beginner lab order:** First complete the root `README.md` Section 0 on the Amazon Linux instance. Then run `source ../lab.env` from this assignment directory before replacing the assignment variables below.


## Objective

Find the latest completed snapshot for a source EBS volume, register an EBS-backed AMI, launch a `t3.micro`, and tag the restored resources.

## Prerequisite

Use a snapshot from Assignment 2 or create one manually. Identify the source volume:

```bash
aws ec2 describe-snapshots --owner-ids self --filters Name=status,Values=completed --query 'Snapshots | sort_by(@, &StartTime)[-5:].{SnapshotId:SnapshotId,VolumeId:VolumeId,StartTime:StartTime}' --output table
export SOURCE_VOLUME_ID=REPLACE_WITH_VOLUME_ID
export SUBNET_ID=REPLACE_WITH_SUBNET_ID
export SECURITY_GROUP_ID=REPLACE_WITH_SECURITY_GROUP_ID
export KEY_NAME=your-key-pair
```

The snapshot, Lambda, AMI, subnet, and instance must be in the same Region. `t3.micro` requires an x86_64 HVM-compatible AMI.

[Screenshot 1: capture the selected completed source snapshot and volume ID.]

## 1. Create the IAM role

```bash
aws iam create-role --role-name Ec2RestoreLambdaRole --assume-role-policy-document file://trust-policy.json
aws iam put-role-policy --role-name Ec2RestoreLambdaRole --policy-name Ec2RestorePolicy --policy-document file://inline-policy.json
export ROLE_ARN=$(aws iam get-role --role-name Ec2RestoreLambdaRole --query Role.Arn --output text)
```

Console: create a Lambda role and add the JSON as an inline policy. `Describe*` APIs generally require `Resource=*`; creation/tagging permissions should be tightened further in production using resource and request-tag conditions.

[Screenshot 2: capture trust relationship and inline policy.]

## 2. Create Lambda

```bash
zip function.zip lambda_function.py
aws lambda create-function \
  --function-name ec2-restore-from-snapshot \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role "$ROLE_ARN" \
  --zip-file fileb://function.zip \
  --timeout 900 \
  --memory-size 256 \
  --environment "Variables={SOURCE_VOLUME_ID=$SOURCE_VOLUME_ID,SUBNET_ID=$SUBNET_ID,SECURITY_GROUP_ID=$SECURITY_GROUP_ID,KEY_NAME=$KEY_NAME,ROOT_DEVICE_NAME=/dev/xvda,INSTANCE_TYPE=t3.micro}"
```

The code waits for the AMI to become available before launching the instance. This is why the timeout is higher than the other assignments.

Console: configure Python 3.12, handler, role, and all environment variables.

[Screenshot 3: capture Lambda configuration.]

## 3. Invoke and verify

```bash
aws lambda invoke --function-name ec2-restore-from-snapshot --payload fileb://test-event.json --cli-binary-format raw-in-base64-out response.json
cat response.json
```

The result contains `snapshot_id`, `image_id`, and `instance_id`.

```bash
export AMI_ID=$(python3.12 -c 'import json; print(json.load(open("response.json"))["image_id"])')
export INSTANCE_ID=$(python3.12 -c 'import json; print(json.load(open("response.json"))["instance_id"])')
aws ec2 describe-images --image-ids "$AMI_ID" --query 'Images[0].{State:State,Root:RootDeviceName,Architecture:Architecture,Mapping:BlockDeviceMappings,Tags:Tags}' --output table
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].{State:State.Name,Type:InstanceType,Image:ImageId,Root:RootDeviceName,Tags:Tags,Volumes:BlockDeviceMappings}' --output table
```

[Screenshot 4: capture test invocation output with snapshot, AMI, and instance IDs.]

[Screenshot 5: capture AMI details showing the root block-device mapping to the snapshot.]

[Screenshot 6: capture the running restored `t3.micro` and `RestoredFrom` tag.]

## 4. CloudWatch logs

```bash
aws logs tail /aws/lambda/ec2-restore-from-snapshot --since 20m
```

[Screenshot 7: capture logs showing the registered AMI and launched instance IDs.]

## 5. Cleanup immediately

Do not delete the source snapshot if it is needed for other assignments.

```bash
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID"
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
aws ec2 deregister-image --image-id "$AMI_ID"
aws lambda delete-function --function-name ec2-restore-from-snapshot
aws iam delete-role-policy --role-name Ec2RestoreLambdaRole --policy-name Ec2RestorePolicy
aws iam delete-role --role-name Ec2RestoreLambdaRole
rm -f function.zip response.json
```

If the restored root volume is not set to delete on termination, delete it after the instance is terminated. Delete only disposable snapshots after confirming they are not referenced by other AMIs.

## Final result screenshot

[Screenshot 8: capture the final AMI and instance details before cleanup, then record the cleanup commands in the README submission notes.]
