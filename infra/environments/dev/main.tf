provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.tags, {
      Project     = var.project_name
      Environment = "dev"
      ManagedBy   = "Terraform"
    })
  }
}

data "aws_caller_identity" "current" {}

locals {
  artifacts_bucket_name = "${var.project_name}-artifacts-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  lambda_archive_path   = "${path.module}/.terraform/hydrosim-app.zip"
}

data "archive_file" "hydrosim_app" {
  type        = "zip"
  output_path = local.lambda_archive_path

  source {
    content  = file("${path.module}/../../../hydrosim/__init__.py")
    filename = "hydrosim/__init__.py"
  }

  source {
    content  = file("${path.module}/../../../hydrosim/aws_handler.py")
    filename = "hydrosim/aws_handler.py"
  }

  source {
    content  = file("${path.module}/../../../hydrosim/engine.py")
    filename = "hydrosim/engine.py"
  }

  source {
    content  = file("${path.module}/../../../hydrosim/service.py")
    filename = "hydrosim/service.py"
  }

  source {
    content  = file("${path.module}/../../../hydrosim/repository.py")
    filename = "hydrosim/repository.py"
  }
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.artifacts_bucket_name
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "artifacts" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.artifacts.arn,
      "${aws_s3_bucket.artifacts.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  policy = data.aws_iam_policy_document.artifacts.json
}

resource "aws_dynamodb_table" "scenarios" {
  name         = "${var.project_name}-scenarios-dev"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "scenario_id"

  attribute {
    name = "scenario_id"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = false
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.project_name}-api-dev"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.project_name}-worker-dev"
  retention_in_days = 7
}

resource "aws_iam_role" "api_lambda" {
  name = "${var.project_name}-api-lambda-dev"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "api_lambda" {
  name = "${var.project_name}-api-access-dev"
  role = aws_iam_role.api_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = [
          "${aws_cloudwatch_log_group.api.arn}:*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.scenarios.arn
      },
      {
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = aws_sfn_state_machine.scenarios.arn
      }
    ]
  })
}

resource "aws_iam_role" "worker_lambda" {
  name = "${var.project_name}-worker-lambda-dev"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "worker_lambda" {
  name = "${var.project_name}-worker-access-dev"
  role = aws_iam_role.worker_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = [
          "${aws_cloudwatch_log_group.worker.arn}:*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.scenarios.arn
      }
    ]
  })
}

resource "aws_lambda_function" "worker" {
  function_name                  = "${var.project_name}-worker-dev"
  role                           = aws_iam_role.worker_lambda.arn
  runtime                        = "python3.12"
  handler                        = "hydrosim.aws_handler.worker_handler"
  filename                       = data.archive_file.hydrosim_app.output_path
  source_code_hash               = data.archive_file.hydrosim_app.output_base64sha256
  memory_size                    = 256
  timeout                        = 30
  architectures                  = ["arm64"]
  reserved_concurrent_executions = 1

  environment {
    variables = {
      SCENARIOS_TABLE = aws_dynamodb_table.scenarios.name
    }
  }

  depends_on = [
    aws_iam_role_policy.worker_lambda,
    aws_cloudwatch_log_group.worker,
  ]
}

resource "aws_iam_role" "step_functions" {
  name = "${var.project_name}-step-functions-dev"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "states.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "step_functions" {
  name = "${var.project_name}-invoke-worker-dev"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.worker.arn
    }]
  })
}

resource "aws_sfn_state_machine" "scenarios" {
  name     = "${var.project_name}-scenarios-dev"
  role_arn = aws_iam_role.step_functions.arn
  type     = "STANDARD"

  definition = jsonencode({
    StartAt = "RunWorker"
    States = {
      RunWorker = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.worker.arn
          "Payload.$"  = "$"
        }
        OutputPath = "$.Payload"
        Retry = [{
          ErrorEquals = [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException",
          ]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        End = true
      }
    }
  })

  depends_on = [aws_iam_role_policy.step_functions]
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.project_name}-api-dev"
  role             = aws_iam_role.api_lambda.arn
  runtime          = "python3.12"
  handler          = "hydrosim.aws_handler.api_handler"
  filename         = data.archive_file.hydrosim_app.output_path
  source_code_hash = data.archive_file.hydrosim_app.output_base64sha256
  memory_size      = 256
  timeout          = 15
  architectures    = ["arm64"]

  environment {
    variables = {
      SCENARIOS_TABLE = aws_dynamodb_table.scenarios.name
      WORKFLOW_ARN    = aws_sfn_state_machine.scenarios.arn
    }
  }

  depends_on = [
    aws_iam_role_policy.api_lambda,
    aws_cloudwatch_log_group.api,
  ]
}

resource "aws_apigatewayv2_api" "http" {
  name          = "${var.project_name}-http-api-dev"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "api" {
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "ANY /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
