# ── Profile ──────────────────────────────────────────────────────────────────
variable "deployment_profile" {
  description = <<-EOT
    "minimal"    - test build. Pod + PVC on the cluster's default StorageClass (EBS) + an internal
                   NLB Service that terminates HTTPS with an ACM certificate. No EFS, no ALB,
                   no security groups, and no AWS Load Balancer Controller or EFS CSI driver needed.
    "enterprise" - production build. EFS storage (survives AZ loss, backed up) + internal ALB via
                   Ingress with a dedicated security group (needs the AWS Load Balancer
                   Controller and EFS CSI driver).
  EOT
  type        = string
  default     = "enterprise"

  validation {
    condition     = contains(["minimal", "enterprise"], var.deployment_profile)
    error_message = "deployment_profile must be \"minimal\" or \"enterprise\"."
  }
}

# ── Existing environment (provided by the cloud team) ────────────────────────
variable "region" {
  description = "AWS region of the EKS cluster."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name of the existing EKS cluster."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC the cluster runs in."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs (>= 2 AZs) used for the EFS mount targets and the internal ALB."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Provide at least two private subnet IDs in different AZs (required by the ALB)."
  }
}

variable "node_security_group_ids" {
  description = <<-EOT
    Additional security group IDs attached to the worker nodes / pods that must reach EFS
    (NFS 2049). The cluster primary security group is always included automatically.
  EOT
  type        = list(string)
  default     = []
}

# ── Application ──────────────────────────────────────────────────────────────
variable "app_name" {
  description = "Name used for all resources, labels and tags."
  type        = string
  default     = "chkhealth"
}

variable "namespace" {
  description = "Kubernetes namespace to create for the application."
  type        = string
  default     = "chkhealth"
}

variable "container_image" {
  description = "Full image URI including tag, e.g. 123456789012.dkr.ecr.us-east-1.amazonaws.com/chkhealth:1.0.0. Avoid 'latest'."
  type        = string
}

variable "image_pull_secret_name" {
  description = "Optional name of an existing imagePullSecret in the namespace (not needed for ECR with node IAM roles)."
  type        = string
  default     = ""
}

variable "cpu_request" {
  type    = string
  default = "250m"
}

variable "memory_request" {
  type    = string
  default = "512Mi"
}

variable "cpu_limit" {
  type    = string
  default = "1"
}

variable "memory_limit" {
  type    = string
  default = "1Gi"
}

variable "replicas" {
  description = "Leave at 1. chkHealth stores metrics in SQLite on a shared volume; more than one replica is unsupported. Set to 0 to stop the app."
  type        = number
  default     = 1

  validation {
    condition     = var.replicas <= 1
    error_message = "chkHealth is single-replica only (SQLite)."
  }
}

# ── Network access ───────────────────────────────────────────────────────────
variable "hostname" {
  description = "Internal DNS name users will browse to (e.g. chkhealth.corp.example.com). Used for the ingress host rule."
  type        = string
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN covering `hostname`, for the ALB HTTPS listener."
  type        = string
}

variable "corporate_cidr_blocks" {
  description = "Corporate network CIDRs (reached via Direct Connect / VPN) allowed to reach the internal ALB/NLB on 443."
  type        = list(string)
}

variable "ingress_class_name" {
  description = "IngressClass handled by the AWS Load Balancer Controller."
  type        = string
  default     = "alb"
}

variable "onprem_cidr_blocks" {
  description = "On-prem CIDRs the pod may reach (Provider-1 MDS, SmartEvent, log servers, LDAP, SMTP). Used only when enable_network_policy = true."
  type        = list(string)
  default     = []
}

variable "enable_network_policy" {
  description = "Create a NetworkPolicy restricting pod egress to DNS, `onprem_cidr_blocks`. Requires a CNI that enforces NetworkPolicy."
  type        = bool
  default     = false
}

# ── Application configuration (non-secret) ───────────────────────────────────
variable "app_env" {
  description = <<-EOT
    Non-secret environment variables for the container (see the application's docs/configuration.md),
    e.g. CP_MDS_PRIMARY, CP_MDS_PRIMARY_LABEL, CP_VERIFY_SSL, LDAP_*, CP_SE_1, CP_MLS_1.
    COOKIE_SECURE=true is set by default because the ALB terminates TLS.
  EOT
  type        = map(string)
  default     = {}
}

# ── RADIUS (optional) ────────────────────────────────────────────────────────
variable "radius_enabled" {
  description = <<-EOT
    Enable RADIUS authentication. Also set RADIUS_HOST, RADIUS_PORT, RADIUS_GROUP_ADMIN,
    RADIUS_GROUP_VIEWER (and optionally RADIUS_HOST_2/RADIUS_PORT_2) in app_env. The shared
    secret is stored in the Kubernetes Secret (key RADIUS_SECRET), never in Terraform.
  EOT
  type        = bool
  default     = false
}

# ── Storage ──────────────────────────────────────────────────────────────────
variable "storage_class_name" {
  description = "minimal profile only: StorageClass for the data volume. Empty uses the cluster default (normally EBS gp3)."
  type        = string
  default     = ""
}

variable "data_volume_size" {
  description = "Size of the /app/data volume."
  type        = string
  default     = "5Gi"
}

variable "efs_kms_key_arn" {
  description = "KMS key ARN for EFS encryption. Empty uses the AWS-managed aws/elasticfilesystem key."
  type        = string
  default     = ""
}

variable "efs_backup_enabled" {
  description = "Enable AWS Backup automatic backups on the EFS file system."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags applied to all AWS resources."
  type        = map(string)
  default     = {}
}
