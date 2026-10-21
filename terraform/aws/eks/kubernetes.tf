locals {
  labels = {
    "app.kubernetes.io/name"       = var.app_name
    "app.kubernetes.io/managed-by" = "terraform"
  }

  app_env = merge(
    { COOKIE_SECURE = "true" },
    var.radius_enabled ? { RADIUS_ENABLED = "true" } : {},
    var.app_env,
  )

  secret_data = merge(
    { SECRET_KEY = "CHANGE-ME", CP_API_KEY = "CHANGE-ME" },
    var.radius_enabled ? { RADIUS_SECRET = "CHANGE-ME" } : {},
  )
}

resource "kubernetes_namespace_v1" "app" {
  metadata {
    name   = var.namespace
    labels = local.labels
  }
}

resource "kubernetes_config_map_v1" "app" {
  metadata {
    name      = "${var.app_name}-config"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels    = local.labels
  }
  data = local.app_env
}

# Empty placeholder. Populate with kubectl after apply (see README). Terraform never
# overwrites the values, so they are not stored in Terraform state or code.
resource "kubernetes_secret_v1" "app" {
  metadata {
    name      = "${var.app_name}-secrets"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels    = local.labels
  }
  data = local.secret_data

  lifecycle { ignore_changes = [data] }
}

# Static EFS provisioning: no StorageClass or dynamic provisioning needed.
resource "kubernetes_persistent_volume_v1" "data" {
  count = local.enterprise ? 1 : 0

  metadata {
    name   = "${var.app_name}-data"
    labels = local.labels
  }
  spec {
    capacity                         = { storage = "5Gi" }
    access_modes                     = ["ReadWriteMany"]
    storage_class_name               = "efs-static"
    persistent_volume_reclaim_policy = "Retain"

    persistent_volume_source {
      csi {
        driver        = "efs.csi.aws.com"
        volume_handle = "${aws_efs_file_system.app[0].id}::${aws_efs_access_point.app[0].id}"
      }
    }
  }

  depends_on = [aws_efs_mount_target.app]
}

# enterprise: binds to the static EFS PV. minimal: dynamically provisioned (EBS on the default StorageClass).
resource "kubernetes_persistent_volume_claim_v1" "data" {
  metadata {
    name      = "${var.app_name}-data"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels    = local.labels
  }
  spec {
    access_modes       = [local.enterprise ? "ReadWriteMany" : "ReadWriteOnce"]
    storage_class_name = local.enterprise ? "efs-static" : (var.storage_class_name != "" ? var.storage_class_name : null)
    volume_name        = local.enterprise ? kubernetes_persistent_volume_v1.data[0].metadata[0].name : null
    resources {
      requests = { storage = var.data_volume_size }
    }
  }

  # EBS uses WaitForFirstConsumer: the claim binds only once the pod is scheduled.
  wait_until_bound = local.enterprise
}

resource "kubernetes_deployment_v1" "app" {
  metadata {
    name      = var.app_name
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels    = local.labels
  }

  spec {
    replicas = var.replicas

    # Recreate: the old pod is stopped before the new one starts, so SQLite is never opened twice.
    strategy { type = "Recreate" }

    selector {
      match_labels = { "app.kubernetes.io/name" = var.app_name }
    }

    template {
      metadata {
        labels = local.labels
        annotations = {
          # Roll the pod when non-secret config changes.
          "checksum/config" = sha256(jsonencode(local.app_env))
        }
      }

      spec {
        dynamic "image_pull_secrets" {
          for_each = var.image_pull_secret_name != "" ? [1] : []
          content {
            name = var.image_pull_secret_name
          }
        }

        security_context {
          run_as_user     = 1000
          run_as_group    = 1000
          run_as_non_root = true
          fs_group        = 1000
        }

        container {
          name              = var.app_name
          image             = var.container_image
          image_pull_policy = "IfNotPresent"

          port {
            container_port = 8080
            name           = "http"
          }

          env_from {
            config_map_ref { name = kubernetes_config_map_v1.app.metadata[0].name }
          }
          env_from {
            secret_ref { name = kubernetes_secret_v1.app.metadata[0].name }
          }

          volume_mount {
            name       = "data"
            mount_path = "/app/data"
          }

          resources {
            requests = { cpu = var.cpu_request, memory = var.memory_request }
            limits   = { cpu = var.cpu_limit, memory = var.memory_limit }
          }

          readiness_probe {
            http_get {
              path = "/healthz"
              port = "http"
            }
            initial_delay_seconds = 10
            period_seconds        = 15
          }

          liveness_probe {
            http_get {
              path = "/healthz"
              port = "http"
            }
            initial_delay_seconds = 30
            period_seconds        = 30
            failure_threshold     = 3
          }

          security_context {
            allow_privilege_escalation = false
            capabilities { drop = ["ALL"] }
          }
        }

        volume {
          name = "data"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.data.metadata[0].name
          }
        }
      }
    }
  }

  # Wait for the first rollout only if the secret has been populated; otherwise do not block apply.
  wait_for_rollout = false
}

resource "kubernetes_service_v1" "app" {
  metadata {
    name      = var.app_name
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels    = local.labels
    annotations = local.enterprise ? {} : {
      "service.beta.kubernetes.io/aws-load-balancer-type"                   = "nlb"
      "service.beta.kubernetes.io/aws-load-balancer-internal"               = "true"
      "service.beta.kubernetes.io/aws-load-balancer-subnets"                = join(",", var.private_subnet_ids)
      "service.beta.kubernetes.io/aws-load-balancer-ssl-cert"               = var.acm_certificate_arn
      "service.beta.kubernetes.io/aws-load-balancer-ssl-ports"              = "443"
      "service.beta.kubernetes.io/aws-load-balancer-ssl-negotiation-policy" = "ELBSecurityPolicy-TLS13-1-2-2021-06"
      "service.beta.kubernetes.io/aws-load-balancer-backend-protocol"       = "tcp"
    }
  }
  spec {
    # enterprise: ClusterIP behind the ALB Ingress. minimal: internal NLB with HTTPS (ACM) terminated at the NLB.
    type                        = local.enterprise ? "ClusterIP" : "LoadBalancer"
    selector                    = { "app.kubernetes.io/name" = var.app_name }
    load_balancer_source_ranges = local.enterprise ? null : var.corporate_cidr_blocks
    port {
      name        = "http"
      port        = local.enterprise ? 80 : 443
      target_port = "http"
    }
  }
}

# Internal ALB via the AWS Load Balancer Controller. scheme=internal => no public IP.
resource "kubernetes_ingress_v1" "app" {
  count = local.enterprise ? 1 : 0

  metadata {
    name      = var.app_name
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels    = local.labels
    annotations = {
      "alb.ingress.kubernetes.io/scheme"                              = "internal"
      "alb.ingress.kubernetes.io/target-type"                         = "ip"
      "alb.ingress.kubernetes.io/subnets"                             = join(",", var.private_subnet_ids)
      "alb.ingress.kubernetes.io/security-groups"                     = aws_security_group.alb[0].id
      "alb.ingress.kubernetes.io/manage-backend-security-group-rules" = "true"
      "alb.ingress.kubernetes.io/certificate-arn"                     = var.acm_certificate_arn
      "alb.ingress.kubernetes.io/listen-ports"                        = jsonencode([{ HTTP = 80 }, { HTTPS = 443 }])
      "alb.ingress.kubernetes.io/ssl-redirect"                        = "443"
      "alb.ingress.kubernetes.io/ssl-policy"                          = "ELBSecurityPolicy-TLS13-1-2-2021-06"
      "alb.ingress.kubernetes.io/backend-protocol"                    = "HTTP"
      "alb.ingress.kubernetes.io/healthcheck-path"                    = "/healthz"
      "alb.ingress.kubernetes.io/healthcheck-port"                    = "traffic-port"
    }
  }

  spec {
    ingress_class_name = var.ingress_class_name

    rule {
      host = var.hostname
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service_v1.app.metadata[0].name
              port { name = "http" }
            }
          }
        }
      }
    }
  }

  wait_for_load_balancer = true
}

resource "kubernetes_network_policy_v1" "app" {
  count = var.enable_network_policy ? 1 : 0

  metadata {
    name      = var.app_name
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    pod_selector {
      match_labels = { "app.kubernetes.io/name" = var.app_name }
    }
    policy_types = ["Ingress", "Egress"]

    # ALB (ip target mode) sends traffic from within the VPC.
    ingress {
      ports {
        port     = "8080"
        protocol = "TCP"
      }
      from {
        ip_block { cidr = data.aws_vpc.this.cidr_block }
      }
    }

    # DNS
    egress {
      ports {
        port     = "53"
        protocol = "UDP"
      }
      ports {
        port     = "53"
        protocol = "TCP"
      }
    }

    # EFS (NFS) inside the VPC
    egress {
      ports {
        port     = "2049"
        protocol = "TCP"
      }
      to {
        ip_block { cidr = data.aws_vpc.this.cidr_block }
      }
    }

    # On-prem Provider-1 / SmartEvent / log servers / LDAP / SMTP
    dynamic "egress" {
      for_each = var.onprem_cidr_blocks
      content {
        to {
          ip_block { cidr = egress.value }
        }
      }
    }
  }
}
