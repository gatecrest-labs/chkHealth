# Creates the secret containers in Secret Manager. Values must be set manually after apply:
#   echo -n "VALUE" | gcloud secrets versions add chkhealth-SECRET_KEY --data-file=-
# See outputs for the secret IDs.

resource "google_secret_manager_secret" "secret_key" {
  secret_id = "${var.app_name}-SECRET_KEY"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret" "cp_api_key" {
  secret_id = "${var.app_name}-CP_API_KEY"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_iam_member" "secret_key_accessor" {
  secret_id = google_secret_manager_secret.secret_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun.email}"
}

resource "google_secret_manager_secret_iam_member" "cp_api_key_accessor" {
  secret_id = google_secret_manager_secret.cp_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun.email}"
}
