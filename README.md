# AWS Lambda Automation Assignments

This repository contains six Python 3.12 AWS Lambda assignments. Each assignment has its own Lambda source, IAM policies, test event, and `README.md` with setup, testing, screenshots, and cleanup instructions.

## Repository layout

```text
aws-lambda-automation-assignments/
├── README.md
├── 01-s3-cleanup/
│   ├── README.md
│   ├── lambda_function.py
│   ├── trust-policy.json
│   ├── inline-policy.json
│   └── test-event.json
├── 02-ebs-snapshot/
├── 03-ec2-auto-tag/
├── 04-cost-alert/
├── 05-ec2-restore/
└── 06-s3-public-audit/
```

## Prerequisites

Use one AWS Region consistently. The examples use `us-east-1`; change `AWS_REGION` everywhere if required.

## 0. Prepare the Amazon Linux 2023 lab first

### 0.0 Connect to the EC2 instance

From the AWS Console, open **EC2 → Instances**, select the Linux instance, and choose **Connect**. You can use **EC2 Instance Connect** if the instance has the required network access, or use the **SSH client** instructions shown by AWS.

For a local SSH client, restrict your private-key permissions and connect as `ec2-user`:

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ec2-user@PUBLIC_IP_ADDRESS
```

The security group should allow SSH port 22 only from **My IP**, not from `0.0.0.0/0`. If the instance has no public IP, use EC2 Instance Connect, Systems Manager Session Manager, or a bastion approved for your lab.

Run these commands on your AWS Linux EC2 instance. Use the `ec2-user` account and do not run the lab as root except for package installation commands that explicitly use `sudo`.

### 0.1 Confirm the operating system

```bash
cat /etc/os-release
uname -m
whoami
```

The expected operating system is Amazon Linux 2023. `x86_64` instances use the x86_64 AWS CLI installer; `aarch64`/Graviton instances use the ARM installer.

### 0.2 Update the instance and install basic tools

```bash
sudo dnf update -y
sudo dnf install -y git zip unzip jq curl tar gzip openssl findutils
```

These packages support source control, Lambda ZIP creation, JSON inspection, downloads, and troubleshooting.

### 0.3 Install or verify AWS CLI v2

Check first because Amazon Linux images may already contain AWS CLI:

```bash
aws --version 2>&1 || true
```

For an x86_64 instance, install the AWS-published CLI v2 bundle if the command is missing or reports version 1:

```bash
if aws --version 2>&1 | grep -q '^aws-cli/1'; then
  sudo dnf remove -y awscli
fi
curl -fsSL https://awscli.amazonaws.com/v2/install.sh | sudo bash -s -- --system
aws --version
```

For an ARM/Graviton instance, use the architecture-specific installer instead:

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
sudo /tmp/aws/install --update
aws --version
```

AWS CLI v2 is installed as a standalone application; do not install it with `pip`.

### 0.4 Install Python 3.12 and create a virtual environment

```bash
sudo dnf install -y python3.12 python3.12-pip python3.12-devel
python3.12 --version
python3.12 -m venv "$HOME/aws-lambda-venv"
source "$HOME/aws-lambda-venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install boto3 botocore
python --version
```

The Lambda source uses Boto3 at runtime, but installing Boto3 in the EC2 virtual environment helps you test imports and run small verification scripts. Do not copy this virtual environment into Lambda ZIP files.

If `dnf` reports that `python3.12` is unavailable, run `sudo dnf search python3.12`, confirm the current Amazon Linux repository configuration, and do not replace the system Python. The assignment runtime must remain Python 3.12.

### 0.5 Create the lab workspace

```bash
mkdir -p "$HOME/aws-lambda-lab"
cd "$HOME/aws-lambda-lab"
# Clone after you push the repository, or copy the repository archive here.
# git clone https://github.com/YOUR_GITHUB_USER/aws-lambda-automation-assignments.git
```

### 0.6 Create the reusable variables file

From the repository root, copy the example file and load it into the current shell:

```bash
cp lab.env.example lab.env
chmod 600 lab.env
vi lab.env
source ./lab.env
echo "$AWS_REGION / $LAMBDA_RUNTIME / $EC2_INSTANCE_TYPE / $ACCOUNT_ID"
```

If `ACCOUNT_ID` is empty, configure credentials first and run `source ./lab.env` again. Use `lab.env` for non-secret lab values such as Region, runtime, instance type, prefixes, and retention days. Never put an access key or secret access key in this repository or in `lab.env`. The file is ignored by Git.

### 0.7 Configure AWS credentials: preferred EC2 role method

The safest method on an EC2 instance is an IAM instance role. It provides temporary credentials automatically and avoids storing an access key or secret key on disk. In the AWS Console:

1. Open **EC2 → Instances** and select the Linux instance.
2. Choose **Actions → Security → Modify IAM role**.
3. Select an existing lab instance profile, or create one with the permissions approved for your training account.
4. Choose **Update IAM role**.
5. On the instance, run:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE
aws sts get-caller-identity
aws configure get region || true
```

If the command returns the expected account and role identity, no access key configuration is needed.

### 0.8 Configure AWS credentials: access key and secret key method for a disposable lab

Use this only if your training setup requires an IAM user access key. Never create access keys for the AWS account root user. AWS recommends temporary credentials or IAM roles instead of long-lived access keys.

In the AWS Console:

1. Open **IAM → Users** and select your dedicated lab IAM user.
2. Open **Security credentials → Access keys → Create access key**.
3. Select **Command Line Interface (CLI)**.
4. Create the key and download the CSV immediately. The secret key is shown only at creation time.
5. Do not upload the CSV to GitHub, email it, or paste it into chat.

On the EC2 instance, configure a named AWS CLI profile. The command prompts for the values so they do not appear in shell history:

```bash
aws configure --profile lab
# AWS Access Key ID: paste the access key ID
# AWS Secret Access Key: paste the secret access key
# Default region name: us-east-1
# Default output format: json
```

Enable the profile for the current shell:

```bash
export AWS_PROFILE=lab
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION="$AWS_REGION"
aws sts get-caller-identity
aws configure list
```

Now uncomment `export AWS_PROFILE=lab` in `lab.env`. Each new SSH session must load the variables again with `source ./lab.env`.

The CLI stores the profile in `~/.aws/credentials` and `~/.aws/config`, not in the Git repository. Protect the files:

```bash
chmod 700 ~/.aws
chmod 600 ~/.aws/credentials ~/.aws/config
```

### 0.9 Confirm access before creating resources

```bash
aws sts get-caller-identity
aws ec2 describe-regions --region "$AWS_REGION" --query "Regions[?RegionName=='$AWS_REGION'].RegionName" --output text
aws s3api list-buckets --query 'Buckets[].Name' --output table
```

If any command returns `AccessDenied`, stop and fix the IAM permissions before continuing. Do not solve an access-denied error by committing credentials or attaching unrestricted policies to Lambda roles.

## 1. Install locally or on the lab instance

Required tools:

* AWS CLI v2
* Python 3.12 or later
* `pip`
* `zip` and `unzip`
* Git

Verify:

```bash
aws --version
python3.12 --version
git --version
aws sts get-caller-identity
export AWS_REGION=us-east-1
aws configure set region "$AWS_REGION"
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "$ACCOUNT_ID / $AWS_REGION"
```

No third-party Python package is required for the source code. Lambda provides Boto3 in the managed runtime, and each function uses only the standard library plus Boto3. For production reproducibility, package a tested Boto3 version as described in the relevant README.

## Official references

* [Install or update AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
* [AWS CLI configuration and credentials](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
* [AWS IAM access-key guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html)
* [Amazon Linux 2023 documentation](https://docs.aws.amazon.com/linux/al2023/ug/what-is-amazon-linux.html)

## Recommended order

Complete Assignment 2 before Assignment 5 because Assignment 5 can reuse an EBS snapshot created by Assignment 2. Complete Assignment 4 and Assignment 6 only a few times because they use paid or security-sensitive services.

## Set a $1 budget alert first

In the AWS Console:

1. Open **Billing and Cost Management → Budgets → Create budget**.
2. Choose **Cost budget**.
3. Set amount to **1 USD**, monthly period, and an email notification at **80%** and **100%**.
4. Confirm the email notification if AWS requests it.
5. Capture the budget page only if your assessor asks for setup evidence; do not include billing account details in a public repository.

## Common Lambda deployment pattern

Each assignment README contains exact commands. The common pattern is:

```bash
zip function.zip lambda_function.py
aws lambda create-function \
  --function-name FUNCTION_NAME \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role ROLE_ARN \
  --zip-file fileb://function.zip
```

For the Lambda console, use **Author from scratch**, runtime **Python 3.12**, handler `lambda_function.lambda_handler`, and the assignment execution role. In **Configuration → Environment variables**, enter the variables shown in that assignment README.
