output "artifacts_bucket_name" {
  description = "S3 bucket for development inputs, outputs, and run artifacts."
  value       = aws_s3_bucket.artifacts.bucket
}

output "artifacts_bucket_arn" {
  description = "ARN of the development artifacts bucket."
  value       = aws_s3_bucket.artifacts.arn
}

output "api_base_url" {
  description = "IAM-authenticated HTTP API endpoint for the development environment."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "scenarios_table_name" {
  description = "DynamoDB table storing scenario state and demo results."
  value       = aws_dynamodb_table.scenarios.name
}

output "scenario_workflow_arn" {
  description = "Step Functions state machine started for each submitted scenario."
  value       = aws_sfn_state_machine.scenarios.arn
}
