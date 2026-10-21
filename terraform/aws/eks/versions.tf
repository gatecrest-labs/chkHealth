terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }

  # The cloud team will normally supply their own remote state. Uncomment and edit.
  # backend "s3" {
  #   bucket         = "REPLACE-tfstate-bucket"
  #   key            = "chkhealth/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "REPLACE-tfstate-lock"
  #   encrypt        = true
  # }
}
