output "ecr_repository_url" {
  description = "Push images here: docker push <url>:<git-sha>"
  value       = aws_ecr_repository.app.repository_url
}

output "nat_gateway_public_ip" {
  description = "Static egress IP — allowlist this on CP MDS, SMTP, RADIUS, and SNMP targets."
  value       = module.vpc.nat_public_ips[0]
}

output "alb_dns_name" {
  description = "Internal ALB hostname — use as the CNAME target in your private hosted zone (e.g. Route 53 Private Hosted Zone for chkhealth.corp.example.com)."
  value       = aws_lb.internal.dns_name
}

output "secret_key_arn" {
  description = "Set value: aws secretsmanager put-secret-value --secret-id <arn> --secret-string \"$(uv run python manage_users.py secret)\""
  value       = aws_secretsmanager_secret.secret_key.arn
}

output "cp_api_key_arn" {
  description = "Set value: aws secretsmanager put-secret-value --secret-id <arn> --secret-string \"YOUR_CP_API_KEY\""
  value       = aws_secretsmanager_secret.cp_api_key.arn
}

output "efs_id" {
  description = "EFS file system ID — reference in aws ecs execute-command troubleshooting."
  value       = aws_efs_file_system.app.id
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.app.name
}

output "next_step" {
  description = "Deployment status hint."
  value = var.container_image == "" ? (
    "Phase 1 complete. Push your image to ${aws_ecr_repository.app.repository_url}:<git-sha>, then re-apply with container_image set."
  ) : "ECS service deployed. See alb_dns_name for the dashboard URL."
}
