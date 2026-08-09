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

<img width="971" height="317" alt="Screenshot 2026-08-09 at 7 58 23 PM" src="https://github.com/user-attachments/assets/c561fbaf-ca0b-49b7-96cb-bc860d158996" />


## 1. Create the IAM role

```bash
aws iam create-role --role-name Ec2RestoreLambdaRole --assume-role-policy-document file://trust-policy.json
aws iam put-role-policy --role-name Ec2RestoreLambdaRole --policy-name Ec2RestorePolicy --policy-document file://inline-policy.json
export ROLE_ARN=$(aws iam get-role --role-name Ec2RestoreLambdaRole --query Role.Arn --output text)
```

Console: create a Lambda role and add the JSON as an inline policy. `Describe*` APIs generally require `Resource=*`; creation/tagging permissions should be tightened further in production using resource and request-tag conditions.

<img width="902" height="489" alt="Screenshot 2026-08-09 at 8 03 19 PM" src="https://github.com/user-attachments/assets/461d4357-1bec-4199-bc23-398c607985df" />

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

<img width="980" height="567" alt="Screenshot 2026-08-09 at 8 25 43 PM" src="https://github.com/user-attachments/assets/8fcc6910-f993-4bd4-9e56-33ad15f5cda8" />


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

<img width="864" height="828" alt="Screenshot 2026-08-09 at 8 29 19 PM" src="https://github.com/user-attachments/assets/c2c7552c-2ada-46c2-bc35-d4bdb85a1d74" />
<img width="827" height="248" alt="Screenshot 2026-08-09 at 8 28 05 PM" src="https://github.com/user-attachments/assets/10aba5d4-c8ce-4c5a-836e-e2d408a30e42" />
<img width="1726" height="523" alt="Screenshot 2026-08-09 at 8 32 44 PM" src="https://github.com/user-attachments/assets/a48aa109-39c3-498d-a5c7-c09e6657a6fb" />



## 4. CloudWatch logs

```bash
aws logs tail /aws/lambda/ec2-restore-from-snapshot --since 20m
```

<img width="1709" height="203" alt="Screenshot 2026-08-09 at 8 31 45 PM" src="https://github.com/user-attachments/assets/1652b0ad-56db-4c37-98e4-280269fcf720" />


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
