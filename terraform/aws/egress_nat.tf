# Private NAT Gateway — gives all traffic to the corporate WAN (wan_cidr_blocks) and Provider-1
# (cp_mds_primary) a single, stable private source IP for firewall allow-listing. Lives in its
# own subnet/route table so its own egress still reaches the VPN/Direct Connect attachment
# directly, instead of looping back through itself via the override routes added later in this file.
#
# Note: wan_cidr_blocks must be at least as specific as any route your VPN/Direct Connect
# attachment propagates — AWS route tables use longest-prefix-match, so a propagated route more
# specific than wan_cidr_blocks still wins over this override for that narrower destination.
# cp_mds_primary's explicit /32 is always the most specific possible, so it is never affected.

locals {
  onprem_egress_cidrs = toset(concat(
    var.wan_cidr_blocks,
    var.cp_mds_primary != "" ? ["${var.cp_mds_primary}/32"] : []
  ))
}

resource "aws_subnet" "nat_gateway" {
  vpc_id            = module.vpc.vpc_id
  cidr_block        = cidrsubnet(cidrsubnet(var.vpc_cidr, 4, 2), 8, 0)
  availability_zone = var.primary_az

  tags = {
    Name = "${var.app_name}-private-nat"
  }
}

resource "aws_route_table" "nat_gateway" {
  vpc_id = module.vpc.vpc_id

  tags = {
    Name = "${var.app_name}-private-nat"
  }
}

resource "aws_route_table_association" "nat_gateway" {
  subnet_id      = aws_subnet.nat_gateway.id
  route_table_id = aws_route_table.nat_gateway.id
}

# If set, these let the NAT gateway's own subnet reach the corporate network directly. If both
# are left empty, this route table has no path to wan_cidr_blocks/cp_mds_primary until the
# network team adds one manually — the NAT gateway resource still creates successfully.
resource "aws_route" "nat_gateway_egress_via_vgw" {
  for_each = var.vpn_gateway_id != "" ? local.onprem_egress_cidrs : toset([])

  route_table_id         = aws_route_table.nat_gateway.id
  destination_cidr_block = each.value
  gateway_id             = var.vpn_gateway_id
}

resource "aws_route" "nat_gateway_egress_via_tgw" {
  for_each = var.transit_gateway_id != "" ? local.onprem_egress_cidrs : toset([])

  route_table_id         = aws_route_table.nat_gateway.id
  destination_cidr_block = each.value
  transit_gateway_id     = var.transit_gateway_id
}

resource "aws_nat_gateway" "private" {
  connectivity_type = "private"
  subnet_id         = aws_subnet.nat_gateway.id

  tags = {
    Name = "${var.app_name}-private-nat"
  }

  lifecycle {
    precondition {
      condition     = !(var.vpn_gateway_id != "" && var.transit_gateway_id != "")
      error_message = "Set only one of vpn_gateway_id or transit_gateway_id, not both."
    }
  }
}

# The ECS task gets its own subnet/route table, separate from module.vpc.private_subnets (which
# the internal ALB also uses, from alb.tf). Redirecting wan_cidr_blocks/cp_mds_primary to the
# private NAT gateway in THAT shared table would also redirect the ALB's own reply traffic to
# every WAN client (the ALB security group only admits wan_cidr_blocks sources, so every client
# is in that range) — breaking inbound access to the app entirely. Isolating the ECS task avoids
# that blast radius.
resource "aws_subnet" "ecs_task" {
  vpc_id            = module.vpc.vpc_id
  cidr_block        = cidrsubnet(cidrsubnet(var.vpc_cidr, 4, 2), 8, 1)
  availability_zone = var.primary_az

  tags = {
    Name = "${var.app_name}-ecs-task"
  }
}

resource "aws_route_table" "ecs_task" {
  vpc_id = module.vpc.vpc_id

  tags = {
    Name = "${var.app_name}-ecs-task"
  }
}

resource "aws_route_table_association" "ecs_task" {
  subnet_id      = aws_subnet.ecs_task.id
  route_table_id = aws_route_table.ecs_task.id
}

# General internet egress (ECR pulls, Secrets Manager, other AWS APIs) — same path the task used
# before, via the module's existing public NAT Gateway. EFS (also in module.vpc.private_subnets)
# stays reachable via the VPC's implicit local route; no explicit route needed for that.
resource "aws_route" "ecs_task_default" {
  route_table_id         = aws_route_table.ecs_task.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = module.vpc.natgw_ids[0]
}

# Redirect the ECS task's egress for wan_cidr_blocks/cp_mds_primary through the private NAT
# gateway — but only if the gateway actually has a path to the corporate network (one of
# vpn_gateway_id/transit_gateway_id is set). This subnet is brand new and starts with no route to
# the corporate network at all (unlike the old shared table, there is no existing VGW-propagated
# or manually-added route to fall back to) — creating these routes with the private NAT gateway
# itself unreachable would blackhole CP MDS/WAN traffic instead of merely leaving it unoptimized.
# Until one of those variables is set, the task has no path to wan_cidr_blocks/cp_mds_primary at
# all; see terraform/aws/README.md's "Static egress IP" section.
resource "aws_route" "ecs_egress_via_private_nat" {
  for_each = (var.vpn_gateway_id != "" || var.transit_gateway_id != "") ? local.onprem_egress_cidrs : toset([])

  route_table_id         = aws_route_table.ecs_task.id
  destination_cidr_block = each.value
  nat_gateway_id         = aws_nat_gateway.private.id
}
