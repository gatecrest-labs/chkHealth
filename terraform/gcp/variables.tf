variable "project_id" {
  description = "GCP project ID. No default — you must set this."
  type        = string
}

variable "region" {
  description = "GCP region for all resources."
  type        = string
  default     = "us-central1"
}

variable "app_name" {
  description = "Name used for all resource names."
  type        = string
  default     = "chkhealth"
}

variable "subnet_cidr" {
  description = "Primary IP range for the application subnet."
  type        = string
  default     = "10.63.0.0/20"
}

variable "proxy_subnet_cidr" {
  description = "Proxy-only subnet required by the Regional Internal Application LB (must not overlap with other ranges)."
  type        = string
  default     = "10.63.16.0/24"
}

variable "connector_range" {
  description = "/28 range (not used elsewhere in the VPC) for the Serverless VPC Access connector."
  type        = string
  default     = "10.63.32.0/28"
}

variable "wan_cidr_blocks" {
  description = <<-EOT
    Corporate WAN CIDR blocks (Cloud VPN or Cloud Interconnect) allowed to reach the internal LB
    on ports 80 and 443. Example: ["10.0.0.0/8"]. The LB has no public IP; this list scopes
    access to known enterprise network ranges arriving through the VPN/Interconnect.
  EOT
  type    = list(string)
  default = []
}

variable "container_image" {
  description = <<-EOT
    Full Artifact Registry image URI (e.g. us-central1-docker.pkg.dev/PROJECT/chkhealth/chkhealth:abc1234).
    Leave empty on the first apply; all supporting infrastructure is created without the Cloud Run service.
    After pushing the image, set this and re-apply.
  EOT
  type    = string
  default = ""
}

variable "ssl_certificate_pem" {
  description = <<-EOT
    PEM-encoded TLS certificate for the internal LB (from your internal PKI or a self-signed cert).
    The certificate CN/SAN must match the hostname you will use to access the app over the WAN.
    Leave empty to skip creating the HTTPS listener; add cert and re-apply when ready.
  EOT
  type      = string
  sensitive = true
  default   = ""
}

variable "ssl_private_key_pem" {
  description = "PEM-encoded private key matching ssl_certificate_pem."
  type        = string
  sensitive   = true
  default     = ""
}

variable "cp_mds_primary" {
  description = "Check Point MDS primary IP address."
  type        = string
  default     = ""
}

variable "cp_mds_primary_label" {
  description = "Human-readable label for the MDS primary shown in the chkhealth UI."
  type        = string
  default     = "HQ MDS (Provider-1)"
}

variable "cp_verify_ssl" {
  description = "Set to \"true\" to verify CP API TLS certificates; \"false\" for self-signed appliance certs."
  type        = string
  default     = "false"
}
