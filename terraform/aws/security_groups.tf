# Security groups use separate aws_security_group_rule resources to break the circular
# reference between the ALB SG (egresses to ECS) and the ECS SG (ingresses from ALB).

resource "aws_security_group" "alb" {
  name        = "${var.app_name}-alb-sg"
  description = "chkhealth internal ALB — corporate WAN inbound only, not internet-facing"
  vpc_id      = module.vpc.vpc_id
}

resource "aws_security_group" "ecs" {
  name        = "${var.app_name}-ecs-sg"
  description = "chkhealth ECS Fargate tasks"
  vpc_id      = module.vpc.vpc_id
}

resource "aws_security_group" "efs" {
  name        = "${var.app_name}-efs-sg"
  description = "chkhealth EFS mount targets"
  vpc_id      = module.vpc.vpc_id
}

# ---- ALB rules ----

resource "aws_security_group_rule" "alb_ingress_https" {
  security_group_id = aws_security_group.alb.id
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = var.wan_cidr_blocks
  description       = "HTTPS from corporate WAN (VPN/Direct Connect)"
}

resource "aws_security_group_rule" "alb_ingress_http" {
  security_group_id = aws_security_group.alb.id
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = var.wan_cidr_blocks
  description       = "HTTP redirect from corporate WAN (VPN/Direct Connect)"
}

resource "aws_security_group_rule" "alb_egress_ecs" {
  security_group_id        = aws_security_group.alb.id
  type                     = "egress"
  from_port                = 8080
  to_port                  = 8080
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs.id
  description              = "Forward to ECS tasks"
}

# ---- ECS task rules ----

resource "aws_security_group_rule" "ecs_ingress_alb" {
  security_group_id        = aws_security_group.ecs.id
  type                     = "ingress"
  from_port                = 8080
  to_port                  = 8080
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
  description              = "HTTP from internal ALB"
}

resource "aws_security_group_rule" "ecs_egress_efs" {
  security_group_id        = aws_security_group.ecs.id
  type                     = "egress"
  from_port                = 2049
  to_port                  = 2049
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.efs.id
  description              = "NFS to EFS mount targets"
}

resource "aws_security_group_rule" "ecs_egress_https" {
  security_group_id = aws_security_group.ecs.id
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "HTTPS to AWS APIs (ECR, Secrets Manager) and CP MDS appliances"
}

# ---- EFS mount target rules ----

resource "aws_security_group_rule" "efs_ingress_ecs" {
  security_group_id        = aws_security_group.efs.id
  type                     = "ingress"
  from_port                = 2049
  to_port                  = 2049
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs.id
  description              = "NFS from ECS tasks"
}
