# VPC spans two AZs (required by the ALB) but only the primary AZ gets a NAT Gateway —
# the same zone-pinning rationale as docs/deployment-aws-ecs.md: EFS and ECS tasks
# all live in the primary AZ to avoid cross-AZ NFS latency and EBS zone-pinning problems.

locals {
  azs = [var.primary_az, var.secondary_az]
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = "${var.app_name}-vpc"
  cidr = var.vpc_cidr

  azs             = local.azs
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i + 8)]

  enable_nat_gateway     = true
  single_nat_gateway     = true  # one NAT Gateway total, in the primary AZ — gives one static egress IP
  one_nat_gateway_per_az = false

  enable_dns_hostnames = true
  enable_dns_support   = true
}
