variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "primary_az" {
  description = "Primary AZ for ECS tasks and the EFS mount target that the task uses."
  type        = string
  default     = "us-east-1a"
}

variable "secondary_az" {
  description = "Second AZ required by the ALB (ALB spans >= 2 AZs) and for a secondary EFS mount target; no ECS task runs here."
  type        = string
  default     = "us-east-1b"
}

variable "app_name" {
  description = "Name used for all resource names and tags."
  type        = string
  default     = "chkhealth"
}

variable "vpc_cidr" {
  description = "CIDR block for the new VPC."
  type        = string
  default     = "10.43.0.0/16"
}

variable "wan_cidr_blocks" {
  description = <<-EOT
    Corporate WAN CIDR blocks (Site-to-Site VPN or Direct Connect) allowed to reach the internal
    ALB on ports 80 and 443. Example: ["10.0.0.0/8"]. The ALB is not internet-facing; this list
    scopes access to known enterprise network ranges.
  EOT
  type        = list(string)
}

variable "task_cpu" {
  description = "Fargate task CPU units."
  type        = string
  default     = "512"
}

variable "task_memory" {
  description = "Fargate task memory in MiB."
  type        = string
  default     = "1024"
}

variable "container_image" {
  description = <<-EOT
    Full ECR image URI including tag (e.g. 123456789012.dkr.ecr.us-east-1.amazonaws.com/chkhealth:abc1234).
    Leave empty on the first apply to create all supporting infrastructure without the ECS service.
    After pushing the image, set this and re-apply — the ECS task definition and service are created then.
  EOT
  type    = string
  default = ""
}

variable "acm_certificate_arn" {
  description = <<-EOT
    ARN of an ACM certificate covering the internal hostname (e.g. chkhealth.corp.example.com).
    Request the cert in ACM with DNS validation before applying. Leave empty to skip the HTTPS
    listener; the ALB will only serve the HTTP→HTTPS redirect until this is set.
  EOT
  type    = string
  default = ""
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

variable "vpn_gateway_id" {
  description = <<-EOT
    Existing Virtual Private Gateway ID (vgw-...) that carries routes to the corporate network.
    Set this so the new private NAT gateway's own subnet can route traffic to wan_cidr_blocks and
    cp_mds_primary. Mutually exclusive with transit_gateway_id. Leave both empty if your network
    team will add this route manually after apply.
  EOT
  type    = string
  default = ""
}

variable "transit_gateway_id" {
  description = <<-EOT
    Existing Transit Gateway attachment ID (tgw-attach-...) that carries routes to the corporate
    network, used instead of vpn_gateway_id when connectivity goes through a Transit Gateway.
    Mutually exclusive with vpn_gateway_id.
  EOT
  type    = string
  default = ""
}

check "onprem_route_target_mutually_exclusive" {
  assert {
    condition     = !(var.vpn_gateway_id != "" && var.transit_gateway_id != "")
    error_message = "Set only one of vpn_gateway_id or transit_gateway_id, not both."
  }
}
