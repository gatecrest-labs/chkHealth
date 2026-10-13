resource "google_kms_key_ring" "app" {
  name     = "${var.app_name}-keyring"
  location = var.region
}

resource "google_kms_crypto_key" "secrets" {
  name     = "secrets"
  key_ring = google_kms_key_ring.app.id

  lifecycle {
    prevent_destroy = true
  }
}

data "google_project" "current" {}

resource "google_kms_crypto_key_iam_member" "cloudrun_sa_encrypt_decrypt" {
  crypto_key_id = google_kms_crypto_key.secrets.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.cloudrun.email}"
}
