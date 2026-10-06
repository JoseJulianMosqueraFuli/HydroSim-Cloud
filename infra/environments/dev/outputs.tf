output "artifacts_bucket_name" {
  description = "S3 bucket for development inputs, outputs, and run artifacts."
  value       = aws_s3_bucket.artifacts.bucket
}

output "artifacts_bucket_arn" {
  description = "ARN of the development artifacts bucket."
  value       = aws_s3_bucket.artifacts.arn
}
