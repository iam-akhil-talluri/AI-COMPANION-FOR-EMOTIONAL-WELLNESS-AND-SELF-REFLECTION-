#=====================================
#SECTION 1: PROVIDER
#=====================================

provider "aws" {
 region = "us-east-1"
}

#=====================================
#SECTION 2: NETWORK
#=====================================

resource "aws_vpc" "capstone_vpc" {
 cidr_block = "10.0.0.0/16"

 tags = {
 Name = "ai-capstone-vpc06"
 }
}


resource "aws_subnet" "public_subnet" {
 vpc_id = aws_vpc.capstone_vpc.id
 cidr_block = "10.0.1.0/24"
 availability_zone = "us-east-1a"

 tags = {
 Name = "Public-AI-Capstone-VPC06"
 }
}

resource "aws_subnet" "private_subnet" {
 vpc_id = aws_vpc.capstone_vpc.id
 cidr_block = "10.0.2.0/24"
 availability_zone = "us-east-1a"

 tags = {
 Name = "Private-AI-Capstone-vp06"
 }
}

resource "aws_internet_gateway" "capstone_igw" {
 vpc_id = aws_vpc.capstone_vpc.id

 tags = {
 Name = "Capstone-AIAgent-igw"
 }
}

resource "aws_route_table" "public_rt" {
 vpc_id = aws_vpc.capstone_vpc.id

 route {
 cidr_block = "0.0.0.0/0"
 gateway_id = aws_internet_gateway.capstone_igw.id
 }

 tags = {
 Name = "Capstone-Public-RoutingTable"
 }
}

resource "aws_route_table_association" "public_rta" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public_rt.id
}

resource "aws_eip" "nat_eip" {
 domain = "vpc"
}

resource "aws_nat_gateway" "capstone_nat_gw" {
 allocation_id = aws_eip.nat_eip.id
 subnet_id = aws_subnet.public_subnet.id

 tags = {
 Name = "capstone-nat-gw"
 }

 depends_on = [aws_internet_gateway.capstone_igw]
}

resource "aws_route" "private_nat_route" {
 route_table_id = aws_route_table.capstone_private_rt.id
 destination_cidr_block = "0.0.0.0/0"
 nat_gateway_id = aws_nat_gateway.capstone_nat_gw.id
}

resource "aws_route_table" "capstone_private_rt" {
 vpc_id = aws_vpc.capstone_vpc.id

 tags = {
 Name = "Capstone-Private-RoutingTable"
 }
}

#=====================================
#SECTION 3: SERVER AND SESSION MANAGER
#=====================================

resource "aws_iam_role" "ec2_ssm_role" {
 name = "capstone-ec2-ssm-role"

 assume_role_policy = jsonencode({
 Version = "2012-10-17"
 Statement = [
 {
 Action = "sts:AssumeRole"
 Effect = "Allow"
 Principal = {
 Service = "ec2.amazonaws.com"
 }
 }
 ]
 })

 tags = {
 Name = "capstone-ec2-ssm-role"
 }
}

resource "aws_iam_role_policy_attachment" "ssm_policy" {
 role = aws_iam_role.ec2_ssm_role.name
 policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2_ssm_profile" {
 name = "capstone-ec2-ssm-profile"
 role = aws_iam_role.ec2_ssm_role.name
}

#Security group with no SSH port open

resource "aws_security_group" "ec2_sg" {
 name = "capstone-ec2-sg"
 description = "Security group for Capstone EC2 instance - SSM access only"
 vpc_id = aws_vpc.capstone_vpc.id

 egress {
 from_port = 0
 to_port = 0
 protocol = "-1"
 cidr_blocks = ["0.0.0.0/0"]
 }

 tags = {
 Name = "capstone-ec2-sg"
 }
}
#-----------------------------------------------
#EC2 Instance: Runs the AI agent application.
#Lives in the private subnet (no public IP),
#reaches the internet through the NAT Gateway,
#and uses the SSM role/profile for secure
#access instead of SSH.
#-----------------------------------------------
resource "aws_instance" "capstone_app_server" {
  ami                    = "ami-0c02fb55956c7d316" # Amazon Linux 2023, us-east-1
  instance_type         = "t3.micro" # Free tier eligible

  subnet_id             = aws_subnet.private_subnet.id
  vpc_security_group_ids = [aws_security_group.ec2_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_ssm_profile.name

  associate_public_ip_address = false

  tags = {
    Name = "capstone-app-server"
  }
}
#-----------------------------------------------
#CloudWatch Log Group: Captures every Session
#Manager connection and command for audit
#purposes. Retained 30 days to manage cost.
#-----------------------------------------------
resource "aws_cloudwatch_log_group" "ssm_session_logs" {
  name = "/capstone/ssm-sessions"
  retention_in_days = 30
}
#-----------------------------------------------
#SSM preference setting that routes all session
#activity to the log group above.
#-----------------------------------------------
resource "aws_ssm_document" "session_logging" {
  name = "SSM-SessionManagerRunShell"
  document_type = "Session"

  content = jsonencode({
    schemaVersion = "1.0"
    description = "Session Manager logging configuration"
    sessionType = "Standard_Stream"
    inputs = {
      cloudWatchLogGroupName = aws_cloudwatch_log_group.ssm_session_logs.name
      cloudWatchEncryptionEnabled = true
      cloudWatchStreamingEnabled = true
    }
  })
}

#=====================================
#SECTION 4: GITHUB DEPLOY AND SECRETS
#=====================================

resource "aws_iam_openid_connect_provider" "github_actions" {
url = "https://token.actions.githubusercontent.com"
client_id_list = ["sts.amazonaws.com"]
 thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github_actions_deploy" {
 name = "capstone-github-actions-role"

 assume_role_policy = jsonencode({
 Version = "2012-10-17"
 Statement = [{
	Effect = "Allow"
	Principal = {
	Federated = aws_iam_openid_connect_provider.github_actions.arn
	}
	Action = "sts:AssumeRoleWithWebIdentity"
	Condition = {
	StringEquals = {
	"token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
	}
	StringLike = {
	"token.actions.githubusercontent.com:sub" = "repo:iam-akhil-talluri/AI-COMPANION-FOR-EMOTIONAL-WELLNESS-AND-SELF-REFLECTION-:ref:refs/heads/Shaheed_Cloud"
	}
	}
	}]
	})
	tags = {
	Name = "capstone-github-actions-role"
	}
	}

resource "aws_iam_role_policy" "github_actions_ssm_deploy" {
 name = "github-actions-ssm-deploy-policy"
 role = aws_iam_role.github_actions_deploy.id

 policy = jsonencode({
 Version = "2012-10-17"
 Statement = [{
 Effect = "Allow"
 Action = [
 "ssm:SendCommand",
 "ssm:GetCommandInvocation"
 ]
 Resource = [
 aws_instance.capstone_app_server.arn,
 "arn:aws:ssm:*:*:document/AWS-RunShellScript"
 ]
 }]
 })
}

resource "aws_secretsmanager_secret" "api_keys" {
 name = "capstone-api-keys"
}

resource "aws_iam_role_policy" "ec2_read_secrets" {
 name = "ec2-read-api-keys-policy"
 role = aws_iam_role.ec2_ssm_role.id

 policy = jsonencode({
 Version = "2012-10-17"
 Statement = [{
 Effect = "Allow"
 Action = ["secretsmanager:GetSecretValue"]
 Resource = aws_secretsmanager_secret.api_keys.arn
 }]
 })
}


#=====================================
#SECTION 5: FRONTEND (S3 AND CLOUDFRONT)
#=====================================
resource "aws_s3_bucket" "frontend" {
 bucket = "shaheed-capstone-frontend-2026"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
 bucket = aws_s3_bucket.frontend.id
 block_public_acls = true
 block_public_policy = true
 ignore_public_acls = true
 restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
 name = "frontend-oac"
 origin_access_control_origin_type = "s3"
 signing_behavior = "always"
 signing_protocol = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
 enabled = true
 default_root_object = "index.html"

 origin {
 domain_name = aws_s3_bucket.frontend.bucket_regional_domain_name
 origin_id = "frontend-s3-origin"
 origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
 }

 default_cache_behavior {
 allowed_methods = ["GET", "HEAD"]
 cached_methods = ["GET", "HEAD"]
 target_origin_id = "frontend-s3-origin"
 viewer_protocol_policy = "redirect-to-https"

 forwarded_values {
 query_string = false
 cookies { forward = "none" }
 }
 }

 restrictions {
 geo_restriction { restriction_type = "none" }
 }

 viewer_certificate {
 cloudfront_default_certificate = true
 }
}

resource "aws_s3_bucket_policy" "frontend" {
 bucket = aws_s3_bucket.frontend.id
 policy = jsonencode({
 Version = "2012-10-17"
 Statement = {
 Effect = "Allow"
 Principal = { Service = "cloudfront.amazonaws.com" }
 Action = "s3:GetObject"
 Resource = "${aws_s3_bucket.frontend.arn}/*"
 Condition = {
 StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn }
 }
 }
 })
}

output "frontend_bucket_name" {
 value = aws_s3_bucket.frontend.id
}

output "cloudfront_distribution_id" {
 value = aws_cloudfront_distribution.frontend.id
}

#=====================================
#SECTION 6: TEAMMATE POLICIES
#=====================================

resource "aws_iam_user_policy" "mensah_ec2_describe" {
  name   = "MensahEm01-EC2Describe"
  user   = "MensahEm01"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ssm:DescribeInstanceInformation"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = [
          "ssm:StartSession",
          "ssm:TerminateSession"
        ]
        Resource = [
          aws_instance.capstone_app_server.arn,
          "arn:aws:ssm::*:document/SSM-SessionManagerRunShell"
        ]
      }
    ]
  })
}
resource "aws_iam_user_policy" "talluri_secrets_list" {
  name   = "TalluriAk02-SecretsList"
  user   = "TalluriAk02"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:ListSecrets"
      Resource = "*"
    }]
  })
}

resource "aws_iam_user_policy" "talluri_read_api_keys" {
  name   = "TalluriAk02-ReadApiKeys"
  user   = "TalluriAk02"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = aws_secretsmanager_secret.api_keys.arn
    }]
  })
}

#-----------------------------------------------
#Individual teammate IAM policies
#-----------------------------------------------
resource "aws_iam_user_policy" "lakshmi_frontend" {
  name = "frontend-ui-access"
  user = "LakshmiCyn03"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.frontend.arn,
          "${aws_s3_bucket.frontend.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = "cloudfront:CreateInvalidation"
        Resource = aws_cloudfront_distribution.frontend.arn
      }
    ]
  })
}

resource "aws_iam_user_policy" "talluri_backend" {
  name = "backend-db-access"
  user = "TalluriAk02"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["ssm:StartSession", "ssm:TerminateSession"]
        Resource = aws_instance.capstone_app_server.arn
      },
      {
        Effect = "Allow"
        Action = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.api_keys.arn
      },
      {
        Effect = "Allow"
        Action = ["logs:GetLogEvents", "logs:DescribeLogStreams"]
        Resource = "${aws_cloudwatch_log_group.ssm_session_logs.arn}:*"
      }
    ]
  })
}

resource "aws_iam_user_policy" "mensah_ai" {
  name = "conversational-ai-access"
  user = "MensahEm01"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["ssm:StartSession", "ssm:TerminateSession"]
        Resource = aws_instance.capstone_app_server.arn
      },
      {
        Effect = "Allow"
        Action = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.api_keys.arn
      }
    ]
  })
}

resource "aws_iam_user_policy" "owens_safety" {
  name = "safety-moderation-access"
  user = "OwensKo05"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["ssm:StartSession", "ssm:TerminateSession"]
        Resource = aws_instance.capstone_app_server.arn
      },
      {
        Effect = "Allow"
        Action = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.api_keys.arn
      }
    ]
  })
}
