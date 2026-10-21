output "efs_file_system_id" {
  value = try(aws_efs_file_system.app[0].id, null)
}

output "efs_access_point_id" {
  value = try(aws_efs_access_point.app[0].id, null)
}

output "alb_security_group_id" {
  value = try(aws_security_group.alb[0].id, null)
}

output "load_balancer_dns_name" {
  description = "Internal ALB (enterprise) or NLB (minimal) DNS name. Give this to the DNS team for a CNAME from `hostname`."
  value = try(
    kubernetes_ingress_v1.app[0].status[0].load_balancer[0].ingress[0].hostname,
    kubernetes_service_v1.app.status[0].load_balancer[0].ingress[0].hostname,
    "pending - run terraform refresh"
  )
}

output "url" {
  value = "https://${var.hostname}"
}

output "set_secrets_command" {
  description = "Run once after the first apply to set the application secrets."
  value       = "kubectl -n ${var.namespace} create secret generic ${var.app_name}-secrets --from-literal=SECRET_KEY=\"$(openssl rand -hex 32)\" --from-literal=CP_API_KEY='<read-only-api-key>'${var.radius_enabled ? " --from-literal=RADIUS_SECRET='<radius-shared-secret>'" : ""} --dry-run=client -o yaml | kubectl apply -f - && kubectl -n ${var.namespace} rollout restart deploy/${var.app_name}"
}
