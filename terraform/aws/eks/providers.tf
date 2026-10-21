provider "aws" {
  region = var.region

  default_tags {
    tags = merge({ Application = var.app_name, ManagedBy = "terraform" }, var.tags)
  }
}

data "aws_eks_cluster" "this" {
  name = var.cluster_name
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.this.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", var.cluster_name, "--region", var.region]
  }
}

data "aws_vpc" "this" {
  id = var.vpc_id
}
