resource "google_service_account" "cloudrun" {
  account_id   = var.app_name
  display_name = "chkhealth Cloud Run service account"
}

# Grant pull access to this project's Artifact Registry repository only (not all registries).
resource "google_artifact_registry_repository_iam_member" "cloudrun_reader" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.app.repository_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.cloudrun.email}"
}
