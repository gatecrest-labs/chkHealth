resource "aws_efs_file_system" "app" {
  creation_token   = var.app_name
  encrypted        = true
  kms_key_id       = aws_kms_key.main.arn
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"

  tags = { Name = var.app_name }
}

# Access point pins the container to UID/GID 1000 (the `app` user in the chkhealth image)
# and creates /chkhealth-data automatically on first mount.
resource "aws_efs_access_point" "app" {
  file_system_id = aws_efs_file_system.app.id

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

# Mount targets in both AZs — the ECS task always runs in the primary AZ but the secondary
# mount target is required if you ever need to move the task or add a second task in future.
resource "aws_efs_mount_target" "primary" {
  file_system_id  = aws_efs_file_system.app.id
  subnet_id       = module.vpc.private_subnets[0]
  security_groups = [aws_security_group.efs.id]
}

resource "aws_efs_mount_target" "secondary" {
  file_system_id  = aws_efs_file_system.app.id
  subnet_id       = module.vpc.private_subnets[1]
  security_groups = [aws_security_group.efs.id]
}
