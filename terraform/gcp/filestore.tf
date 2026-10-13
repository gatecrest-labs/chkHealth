# Filestore Basic HDD is the only GCP-native NFS option Cloud Run supports for SQLite.
# Minimum capacity is 1 TB (~$100/mo at us-central1 rates) regardless of actual data size.
# See docs/deployment-gcp-cloudrun.md for the cost discussion.

resource "google_filestore_instance" "app" {
  name     = var.app_name
  location = "${var.region}-a"
  tier     = "BASIC_HDD"

  file_shares {
    name        = "data"
    capacity_gb = 1024
  }

  networks {
    network = google_compute_network.vpc.name
    modes   = ["MODE_IPV4"]
  }
}
