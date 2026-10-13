resource "aws_kms_key" "main" {
  description             = "chkhealth data encryption (EFS at-rest, Secrets Manager)"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "main" {
  name          = "alias/${var.app_name}"
  target_key_id = aws_kms_key.main.key_id
}
