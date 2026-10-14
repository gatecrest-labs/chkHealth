# Private NAT Gateway — gives all traffic to the corporate WAN (wan_cidr_blocks) and Provider-1
# (cp_mds_primary) a single, stable private source IP for firewall allow-listing. Lives in its
# own subnet/route table so its own egress still reaches the VPN/Direct Connect attachment
# directly, instead of looping back through itself via the override routes added later in this file.

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

# Redirect the ECS task's own egress for wan_cidr_blocks/cp_mds_primary through the private NAT
# gateway. Static routes take precedence over propagated/attachment routes for the same
# destination, so this works regardless of whether the existing path was VGW route propagation
# or a manually-added TGW static route — it does not require knowing which.
#
# Keyed by index into module.vpc.private_route_table_ids, not by the route table ID itself: on a
# first apply those IDs aren't known until apply, and for_each requires statically-known keys.
# The list's length is always known at plan time (driven by single_nat_gateway/one_nat_gateway_per_az).
locals {
  ecs_override_routes = {
    for pair in setproduct(range(length(module.vpc.private_route_table_ids)), local.onprem_egress_cidrs) :
    "${pair[0]}|${pair[1]}" => {
      route_table_id = module.vpc.private_route_table_ids[pair[0]]
      cidr           = pair[1]
    }
  }
}

resource "aws_route" "ecs_egress_via_private_nat" {
  for_each = local.ecs_override_routes

  route_table_id         = each.value.route_table_id
  destination_cidr_block = each.value.cidr
  nat_gateway_id         = aws_nat_gateway.private.id
}
