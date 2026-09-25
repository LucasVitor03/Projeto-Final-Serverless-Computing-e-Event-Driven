terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
    null = { source  = "hashicorp/null", version = "~> 3.0" }
  }
  backend "s3" {
    bucket         = "puc-serverless-s3-tfstate"
    key            = "projeto-final/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

provider "aws" { region = var.aws_region }

# DLQ — recebe pedidos que falharam
resource "aws_sqs_queue" "dlq" {
  name                       = "${var.project_name}-dlq"
  visibility_timeout_seconds = 60
}

# Empacota as funções
data "archive_file" "order_entry" {
  type        = "zip"
  source_dir  = "${path.module}/../functions"
  output_path = "${path.module}/../functions/order_entry.zip"
  excludes    = ["*.zip", "requirements.txt"]
}

data "archive_file" "reserve_stock" {
  type        = "zip"
  source_dir  = "${path.module}/../functions"
  output_path = "${path.module}/../functions/reserve_stock.zip"
  excludes    = ["*.zip", "requirements.txt"]
}

data "archive_file" "charge_payment" {
  type        = "zip"
  source_dir  = "${path.module}/../functions"
  output_path = "${path.module}/../functions/charge_payment.zip"
  excludes    = ["*.zip", "requirements.txt"]
}

data "archive_file" "ship_order" {
  type        = "zip"
  source_dir  = "${path.module}/../functions"
  output_path = "${path.module}/../functions/ship_order.zip"
  excludes    = ["*.zip", "requirements.txt"]
}

data "archive_file" "ai_analyzer" {
  type        = "zip"
  source_dir  = "${path.module}/../functions"
  output_path = "${path.module}/../functions/ai_analyzer.zip"
  excludes    = ["*.zip", "requirements.txt"]
}

# Lambdas do pipeline
resource "aws_lambda_function" "reserve_stock" {
  function_name    = "${var.project_name}-reserve-stock"
  filename         = data.archive_file.reserve_stock.output_path
  source_code_hash = data.archive_file.reserve_stock.output_base64sha256
  handler          = "reserve_stock.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_exec.arn
  timeout          = 30
  tracing_config { mode = "Active" }
}

resource "aws_lambda_function" "charge_payment" {
  function_name    = "${var.project_name}-charge-payment"
  filename         = data.archive_file.charge_payment.output_path
  source_code_hash = data.archive_file.charge_payment.output_base64sha256
  handler          = "charge_payment.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_exec.arn
  timeout          = 30
  tracing_config { mode = "Active" }
}

resource "aws_lambda_function" "ship_order" {
  function_name    = "${var.project_name}-ship-order"
  filename         = data.archive_file.ship_order.output_path
  source_code_hash = data.archive_file.ship_order.output_base64sha256
  handler          = "ship_order.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_exec.arn
  timeout          = 30
  tracing_config { mode = "Active" }
}

# Lambda AIOps — consome DLQ e analisa com Bedrock
resource "aws_lambda_function" "ai_analyzer" {
  function_name    = "${var.project_name}-ai-analyzer"
  filename         = data.archive_file.ai_analyzer.output_path
  source_code_hash = data.archive_file.ai_analyzer.output_base64sha256
  handler          = "ai_analyzer.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_exec.arn
  timeout          = 60
  tracing_config { mode = "Active" }
}

# Conecta DLQ como gatilho do ai_analyzer
resource "aws_lambda_event_source_mapping" "dlq_trigger" {
  event_source_arn = aws_sqs_queue.dlq.arn
  function_name    = aws_lambda_function.ai_analyzer.arn
  batch_size       = 1
}

# Step Functions
locals {
  workflow_definition = templatefile(
    "${path.module}/../workflow/order_pipeline.asl.json",
    {
      reserve_stock_arn  = aws_lambda_function.reserve_stock.arn
      charge_payment_arn = aws_lambda_function.charge_payment.arn
      ship_order_arn     = aws_lambda_function.ship_order.arn
      dlq_url            = aws_sqs_queue.dlq.url
    }
  )
}

resource "aws_sfn_state_machine" "order_pipeline" {
  name       = var.project_name
  role_arn   = aws_iam_role.sfn_exec.arn
  definition = local.workflow_definition
  tracing_configuration { enabled = true }
}

# Lambda order-entry
resource "aws_lambda_function" "order_entry" {
  function_name    = "${var.project_name}-order-entry"
  filename         = data.archive_file.order_entry.output_path
  source_code_hash = data.archive_file.order_entry.output_base64sha256
  handler          = "order_entry.handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_exec.arn
  timeout          = 30
  tracing_config { mode = "Active" }
  environment {
    variables = { STATE_MACHINE_ARN = aws_sfn_state_machine.order_pipeline.arn }
  }
}

resource "aws_lambda_function_url" "order_entry" {
  function_name      = aws_lambda_function.order_entry.function_name
  authorization_type = "NONE"
  cors {
    allow_credentials = false
    allow_origins     = ["*"]
    allow_methods     = ["POST"]
    allow_headers     = ["Content-Type"]
    max_age           = 300
  }
}

resource "aws_lambda_permission" "order_entry_public" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.order_entry.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# CloudWatch Alarm
resource "aws_cloudwatch_metric_alarm" "pedidos_na_dlq" {
  alarm_name          = "${var.project_name}-pedidos-na-dlq"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "PedidosNaDLQ"
  namespace           = "OrderPipeline"
  period              = 300
  statistic           = "Sum"
  threshold           = 3
  treat_missing_data  = "notBreaching"
}