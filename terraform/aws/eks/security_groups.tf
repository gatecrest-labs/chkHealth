# Enterprise profile only. Security group for the internal ALB. Reachable only from corporate CIDRs.
resource "aws_security_group" "alb" {
  count       = local.enterprise ? 1 : 0
  name_prefix = "${var.app_name}-alb-"
  description = "Internal ALB for ${var.app_name} - corporate network only"
  vpc_id      = var.vpc_id

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  for_each = local.enterprise ? toset(var.corporate_cidr_blocks) : toset([])

  security_group_id = aws_security_group.alb[0].id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS from corporate network"
}

resource "aws_vpc_security_group_ingress_rule" "alb_http_redirect" {
  for_each = local.enterprise ? toset(var.corporate_cidr_blocks) : toset([])

  security_group_id = aws_security_group.alb[0].id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "HTTP (redirected to HTTPS) from corporate network"
}

# The controller adds the ALB -> pod rule itself (manage-backend-security-group-rules).
# Egress is limited to the VPC.
resource "aws_vpc_security_group_egress_rule" "alb_to_vpc" {
  count             = local.enterprise ? 1 : 0
  security_group_id = aws_security_group.alb[0].id
  cidr_ipv4         = data.aws_vpc.this.cidr_block
  ip_protocol       = "tcp"
  from_port         = 8080
  to_port           = 8080
  description       = "ALB to pods"
}
