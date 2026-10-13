output "artifact_registry_repo" {
  description = "Push images here: docker push <repo>/chkhealth:<git-sha>"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}

output "nat_egress_ip" {
  description = "Static egress IP — allowlist this on CP MDS, SMTP, RADIUS, and SNMP targets."
  value       = google_compute_address.nat_egress.address
}

output "ingress_static_ip" {
  description = "Reserved internal IP for the dashboard LB. Point your internal DNS CNAME/A record here. This IP is stable until the resource is destroyed."
  value       = google_compute_address.ingress_internal.address
}

output "secret_key_id" {
  description = "Set value: echo -n \"$(gcloud run ... manage_users.py secret)\" | gcloud secrets versions add chkhealth-SECRET_KEY --data-file=-"
  value       = google_secret_manager_secret.secret_key.secret_id
}

output "cp_api_key_id" {
  description = "Set value: echo -n \"YOUR_CP_API_KEY\" | gcloud secrets versions add chkhealth-CP_API_KEY --data-file=-"
  value       = google_secret_manager_secret.cp_api_key.secret_id
}

output "configure_gcloud" {
  description = "Authenticate gcloud for Cloud Run management."
  value       = "gcloud run services describe ${var.app_name} --region ${var.region} --project ${var.project_id}"
}

output "next_step" {
  description = "Deployment status hint."
  value = var.container_image == "" ? (
    "Phase 1 complete. Push your image to ${var.region}-docker.pkg.dev/${var.project_id}/${var.app_name}/chkhealth:<git-sha>, then re-apply with container_image set."
  ) : "Cloud Run service deployed. See ingress_static_ip for the dashboard IP."
}
