# Creates the secret containers in Secrets Manager. Values must be set manually after apply:
#   aws secretsmanager put-secret-value --secret-id <arn> --secret-string "VALUE"
# See outputs for the ARNs.

resource "aws_secretsmanager_secret" "secret_key" {
  name       = "${var.app_name}/SECRET_KEY"
  kms_key_id = aws_kms_key.main.arn
}

resource "aws_secretsmanager_secret" "cp_api_key" {
  name       = "${var.app_name}/CP_API_KEY"
  kms_key_id = aws_kms_key.main.arn
}
