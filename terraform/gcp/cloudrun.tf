# Cloud Run service is deferred until container_image is set — the image must exist in
# Artifact Registry before Cloud Run can deploy it. Run `terraform apply` once to create
# all supporting infrastructure, push the image, then re-apply with container_image set.

resource "google_cloud_run_v2_service" "app" {
  count    = var.container_image != "" ? 1 : 0
  name     = var.app_name
  location = var.region

  # INTERNAL_AND_CLOUD_LOAD_BALANCING: accepts traffic from within the VPC (via VPN/Interconnect)
  # AND from the internal LB. Does not accept public internet traffic.
  ingress = "INGRESS_TRAFFIC_INTERNAL_AND_CLOUD_LOAD_BALANCING"

  template {
    service_account = google_service_account.cloudrun.email

    scaling {
      min_instance_count = 1  # keep warm; chkHealth starts background schedulers on startup
      max_instance_count = 1  # single-replica constraint — SQLite cannot support concurrent writers
    }

    volumes {
      name = "data"
      nfs {
        server    = google_filestore_instance.app.networks[0].ip_addresses[0]
        path      = "/data"
        read_only = false
      }
    }

    vpc_access {
      connector = google_vpc_access_connector.app.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "COOKIE_SECURE"
        value = "true"
      }

      env {
        name  = "CP_MDS_PRIMARY"
        value = var.cp_mds_primary
      }

      env {
        name  = "CP_MDS_PRIMARY_LABEL"
        value = var.cp_mds_primary_label
      }

      env {
        name  = "CP_VERIFY_SSL"
        value = var.cp_verify_ssl
      }

      env {
        name  = "CP_TIMEOUT"
        value = "30"
      }

      env {
        name  = "GAIA_TIMEOUT"
        value = "15"
      }

      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secret_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "CP_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.cp_api_key.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "data"
        mount_path = "/app/data"
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 10
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.secret_key_accessor,
    google_secret_manager_secret_iam_member.cp_api_key_accessor,
    google_vpc_access_connector.app,
  ]
}

# Allow the internal LB (and VPC-internal callers) to invoke the Cloud Run service
# without IAM authentication. Network-level security is provided by the ingress restriction above.
resource "google_cloud_run_v2_service_iam_member" "internal_invoker" {
  count    = var.container_image != "" ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
