# Private-nodes VPC with Cloud NAT (static egress IP) and a Serverless VPC Access connector
# for Cloud Run → Filestore NFS. The proxy-only subnet is required by the Regional Internal
# Application LB used for the static ingress IP.

resource "google_compute_network" "vpc" {
  name                    = "${var.app_name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "app" {
  name          = "${var.app_name}-subnet"
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.vpc.id

  private_ip_google_access = true  # allows Cloud Run / VPC connector to reach Google APIs without NAT
}

# Required by the Regional Internal Application LB (INTERNAL_MANAGED scheme).
resource "google_compute_subnetwork" "proxy_only" {
  name          = "${var.app_name}-proxy-subnet"
  ip_cidr_range = var.proxy_subnet_cidr
  region        = var.region
  network       = google_compute_network.vpc.id
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
}

# Static egress IP — hand this to your network team for CP MDS/SMTP/RADIUS/SNMP allowlisting.
resource "google_compute_address" "nat_egress" {
  name   = "${var.app_name}-nat-egress"
  region = var.region
}

resource "google_compute_router" "nat" {
  name    = "${var.app_name}-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${var.app_name}-nat"
  router                             = google_compute_router.nat.name
  region                             = var.region
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.nat_egress.self_link]
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# Serverless VPC Access connector — lets Cloud Run reach Filestore over NFS within the VPC.
resource "google_vpc_access_connector" "app" {
  name          = var.app_name
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.connector_range
  min_instances = 2
  max_instances = 3
}

# ---- Firewall rules ----

# Allow WAN traffic (arriving via Cloud VPN / Interconnect) to reach the internal LB.
resource "google_compute_firewall" "allow_wan_to_lb" {
  count   = length(var.wan_cidr_blocks) > 0 ? 1 : 0
  name    = "${var.app_name}-allow-wan-lb"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = var.wan_cidr_blocks
}

# Allow NFS from the VPC connector range to Filestore (custom VPC has no default allow-all rule).
resource "google_compute_firewall" "allow_nfs" {
  name    = "${var.app_name}-allow-nfs"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["2049"]
  }

  source_ranges = [var.connector_range]
}

# Allow Google health-check probers to reach backends (standard requirement for GCP LBs).
resource "google_compute_firewall" "allow_health_checks" {
  name    = "${var.app_name}-allow-health-checks"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8080"]
  }

  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]
}
