output "api_url" {
  description = "URL pública da API"
  value       = aws_lambda_function_url.order_entry.function_url
}

output "frontend_url" {
  description = "URL do site estático no S3"
  value       = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.url
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.order_pipeline.arn
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.bucket
}