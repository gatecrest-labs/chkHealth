resource "google_artifact_registry_repository" "app" {
  repository_id = var.app_name
  location      = var.region
  format        = "DOCKER"
}
