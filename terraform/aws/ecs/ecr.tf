resource "aws_ecr_repository" "app" {
  name                 = var.app_name
  image_tag_mutability = "IMMUTABLE"  # forces real tags (git SHA/semver), prevents silent :latest overwrites

  image_scanning_configuration {
    scan_on_push = true
  }
}
