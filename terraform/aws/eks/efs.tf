locals {
  enterprise = var.deployment_profile == "enterprise"
}

# Persistent storage for /app/data (users.json, groups.json, app_settings.json, metrics.db).

resource "aws_security_group" "efs" {
  count       = local.enterprise ? 1 : 0
  name_prefix = "${var.app_name}-efs-"
  description = "NFS from EKS nodes to the ${var.app_name} EFS"
  vpc_id      = var.vpc_id

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "efs_nfs" {
  for_each = local.enterprise ? toset(concat([data.aws_eks_cluster.this.vpc_config[0].cluster_security_group_id], var.node_security_group_ids)) : toset([])

  security_group_id            = aws_security_group.efs[0].id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 2049
  to_port                      = 2049
  description                  = "NFS from ${each.value}"
}

resource "aws_efs_file_system" "app" {
  count            = local.enterprise ? 1 : 0
  creation_token   = var.app_name
  encrypted        = true
  kms_key_id       = var.efs_kms_key_arn != "" ? var.efs_kms_key_arn : null
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"

  tags = { Name = var.app_name }
}

resource "aws_efs_mount_target" "app" {
  for_each = local.enterprise ? { for idx, id in var.private_subnet_ids : tostring(idx) => id } : {}

  file_system_id  = aws_efs_file_system.app[0].id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs[0].id]
}

# Pins all access to uid/gid 1000 (the `app` user in the image), rooted at /chkhealth-data.
resource "aws_efs_access_point" "app" {
  count          = local.enterprise ? 1 : 0
  file_system_id = aws_efs_file_system.app[0].id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/chkhealth-data"
    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "755"
    }
  }

  tags = { Name = var.app_name }
}

resource "aws_efs_backup_policy" "app" {
  count          = local.enterprise ? 1 : 0
  file_system_id = aws_efs_file_system.app[0].id

  backup_policy {
    status = var.efs_backup_enabled ? "ENABLED" : "DISABLED"
  }
}
