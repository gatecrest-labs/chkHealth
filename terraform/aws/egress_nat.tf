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
