resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.app_name}"
  retention_in_days = 30
}

resource "aws_ecs_cluster" "app" {
  name = var.app_name
}

# Task definition and service are deferred until container_image is set — the image must
# exist in ECR before ECS can pull it. Run `terraform apply` once to create all supporting
# infrastructure, push the image, then re-apply with container_image set in tfvars.
resource "aws_ecs_task_definition" "app" {
  count = var.container_image != "" ? 1 : 0

  family                   = var.app_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name  = var.app_name
    image = var.container_image
    portMappings = [{
      containerPort = 8080
      protocol      = "tcp"
    }]
    environment = [
      { name = "COOKIE_SECURE",        value = "true" },
      { name = "CP_MDS_PRIMARY",       value = var.cp_mds_primary },
      { name = "CP_MDS_PRIMARY_LABEL", value = var.cp_mds_primary_label },
      { name = "CP_VERIFY_SSL",        value = var.cp_verify_ssl },
      { name = "CP_TIMEOUT",           value = "30" },
      { name = "GAIA_TIMEOUT",         value = "15" },
    ]
    secrets = [
      { name = "SECRET_KEY", valueFrom = aws_secretsmanager_secret.secret_key.arn },
      { name = "CP_API_KEY", valueFrom = aws_secretsmanager_secret.cp_api_key.arn },
    ]
    mountPoints = [{
      sourceVolume  = "${var.app_name}-data"
      containerPath = "/app/data"
      readOnly      = false
    }]
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')\" || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.app.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "ecs"
      }
    }
    essential = true
  }])

  volume {
    name = "${var.app_name}-data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.app.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.app.id
        iam             = "ENABLED"
      }
    }
  }
}

resource "aws_ecs_service" "app" {
  count = var.container_image != "" ? 1 : 0

  name                   = var.app_name
  cluster                = aws_ecs_cluster.app.id
  task_definition        = aws_ecs_task_definition.app[0].arn
  desired_count          = 1
  launch_type            = "FARGATE"
  enable_execute_command = true

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = var.app_name
    container_port   = 8080
  }

  network_configuration {
    subnets          = [module.vpc.private_subnets[0]]  # primary AZ only
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  depends_on = [aws_lb_listener.http_redirect, aws_lb_listener.https]

  lifecycle {
    # Allow `aws ecs update-service --force-new-deployment` to push new image tags
    # without Terraform overwriting the task definition revision on next apply.
    ignore_changes = [task_definition]
  }
}
