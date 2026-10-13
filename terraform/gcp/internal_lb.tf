# Regional Internal Application LB (INTERNAL_MANAGED) with a Serverless NEG backend
# pointing at the Cloud Run service. Provides a stable reserved private IP reachable
# from the corporate WAN via Cloud VPN or Cloud Interconnect.
#
# The HTTPS listener (port 443) and HTTP→HTTPS redirect (port 80) are created when
# ssl_certificate_pem is provided. The static IP and NEG are always created so that
# you know the ingress IP before obtaining the TLS certificate.

# Reserved internal IP — this is the stable ingress IP for the chkhealth dashboard.
resource "google_compute_address" "ingress_internal" {
  name         = "${var.app_name}-ingress"
  region       = var.region
  subnetwork   = google_compute_subnetwork.app.id
  address_type = "INTERNAL"
  purpose      = "SHARED_LOADBALANCER_VIP"
}

# Serverless NEG — references the Cloud Run service by name. Can be created before Cloud Run
# is deployed; traffic simply returns 404 until the service exists.
resource "google_compute_region_network_endpoint_group" "cloudrun" {
  name                  = "${var.app_name}-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = var.app_name
  }
}

resource "google_compute_region_backend_service" "app" {
  name                  = var.app_name
  region                = var.region
  load_balancing_scheme = "INTERNAL_MANAGED"
  protocol              = "HTTPS"  # Cloud Run always serves HTTPS

  backend {
    group = google_compute_region_network_endpoint_group.cloudrun.id
  }
}

resource "google_compute_region_url_map" "app" {
  name            = var.app_name
  region          = var.region
  default_service = google_compute_region_backend_service.app.id
}

# ---- HTTPS listener (requires ssl_certificate_pem to be set) ----

locals {
  ssl_configured = var.ssl_certificate_pem != "" && var.ssl_private_key_pem != ""
}

resource "google_compute_region_ssl_certificate" "app" {
  count       = local.ssl_configured ? 1 : 0
  name        = var.app_name
  region      = var.region
  certificate = var.ssl_certificate_pem
  private_key = var.ssl_private_key_pem
}

resource "google_compute_region_target_https_proxy" "app" {
  count            = local.ssl_configured ? 1 : 0
  name             = var.app_name
  region           = var.region
  url_map          = google_compute_region_url_map.app.id
  ssl_certificates = [google_compute_region_ssl_certificate.app[0].id]
}

resource "google_compute_forwarding_rule" "https" {
  count                 = local.ssl_configured ? 1 : 0
  name                  = "${var.app_name}-https"
  region                = var.region
  ip_address            = google_compute_address.ingress_internal.id
  ip_protocol           = "TCP"
  port_range            = "443"
  target                = google_compute_region_target_https_proxy.app[0].id
  load_balancing_scheme = "INTERNAL_MANAGED"
  network               = google_compute_network.vpc.id
  subnetwork            = google_compute_subnetwork.app.id

  depends_on = [google_compute_subnetwork.proxy_only]
}

# ---- HTTP → HTTPS redirect (always created once ssl is configured) ----

resource "google_compute_region_url_map" "http_redirect" {
  count  = local.ssl_configured ? 1 : 0
  name   = "${var.app_name}-http-redirect"
  region = var.region

  default_url_redirect {
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    https_redirect         = true
    strip_query            = false
  }
}

resource "google_compute_region_target_http_proxy" "redirect" {
  count   = local.ssl_configured ? 1 : 0
  name    = "${var.app_name}-http-redirect"
  region  = var.region
  url_map = google_compute_region_url_map.http_redirect[0].id
}

resource "google_compute_forwarding_rule" "http_redirect" {
  count                 = local.ssl_configured ? 1 : 0
  name                  = "${var.app_name}-http-redirect"
  region                = var.region
  ip_address            = google_compute_address.ingress_internal.id
  ip_protocol           = "TCP"
  port_range            = "80"
  target                = google_compute_region_target_http_proxy.redirect[0].id
  load_balancing_scheme = "INTERNAL_MANAGED"
  network               = google_compute_network.vpc.id
  subnetwork            = google_compute_subnetwork.app.id

  depends_on = [google_compute_subnetwork.proxy_only]
}
