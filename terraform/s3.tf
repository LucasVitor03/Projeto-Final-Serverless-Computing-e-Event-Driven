# Bucket para o frontend estático
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}"
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  index_document { suffix = "index.html" }
  error_document { key = "index.html" }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  depends_on = [aws_s3_bucket_public_access_block.frontend]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadGetObject"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
    }]
  })
}

# Atualiza a URL no index.html e faz upload para o S3
# automaticamente após cada terraform apply
resource "null_resource" "frontend_deploy" {
  triggers = {
    # Roda novamente sempre que a Function URL mudar
    api_url = aws_lambda_function_url.order_entry.function_url
  }

  provisioner "local-exec" {
    command = <<-EOT
      sed -i 's|FUNCTION_URL_PLACEHOLDER|${aws_lambda_function_url.order_entry.function_url}|g' ../frontend/index.html
      sed -i 's|https://[a-z0-9]*\.lambda-url\.us-east-1\.on\.aws/|${aws_lambda_function_url.order_entry.function_url}|g' ../frontend/index.html
      aws s3 cp ../frontend/index.html s3://${aws_s3_bucket.frontend.bucket}/index.html --content-type "text/html" --region us-east-1
      echo "Frontend deployado automaticamente com URL: ${aws_lambda_function_url.order_entry.function_url}"
    EOT
  }

  depends_on = [
    aws_s3_bucket_policy.frontend,
    aws_lambda_function_url.order_entry
  ]
}