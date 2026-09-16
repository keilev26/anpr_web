output "url" {
  description = "Dashboard y API: https://<esto>/ y https://<esto>/api/"
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "detections_endpoint" {
  description = "Adonde envía la Raspberry sus ráfagas"
  value       = "https://${aws_cloudfront_distribution.main.domain_name}/api/v1/detections"
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "web_bucket" {
  value = aws_s3_bucket.web.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.infer.repository_url
}

output "ssm_prefix" {
  value = local.ssm_prefix
}

output "api_function_name" {
  value = aws_lambda_function.api.function_name
}

output "inference_enabled" {
  value = local.infer_enabled
}
