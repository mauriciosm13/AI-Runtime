locals {
  container_name = "api"

  container_environment = [
    for key, value in var.container_environment : {
      name  = key
      value = value
    }
  ]

  # Each entry pulls one JSON key out of the same Secrets Manager secret
  # (secrets.tf); ECS resolves these into plain environment variables before
  # the container starts, so Settings never sees a difference from a literal
  # `environment` entry.
  container_secrets = [
    for name, json_key in {
      AI_RUNTIME_DATABASE_URL      = "database_url"
      AI_RUNTIME_REDIS_URL         = "redis_url"
      AI_RUNTIME_OPENAI_API_KEY    = "openai_api_key"
      AI_RUNTIME_ANTHROPIC_API_KEY = "anthropic_api_key"
      AI_RUNTIME_GEMINI_API_KEY    = "gemini_api_key"
      } : {
      name      = name
      valueFrom = "${aws_secretsmanager_secret.app.arn}:${json_key}::"
    }
  ]
}

resource "aws_ecs_task_definition" "api" {
  family                   = local.name_prefix
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        },
      ]

      environment = local.container_environment
      secrets     = local.container_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = local.container_name
        }
      }
    },
  ])

  tags = {
    Name = local.name_prefix
  }
}

resource "aws_ecs_service" "api" {
  name            = local.name_prefix
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  # The load balancer needs the task reachable before it starts health checking,
  # and the target group already health checks GET /health on port 8000.
  health_check_grace_period_seconds = var.health_check_grace_period_seconds

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = local.container_name
    container_port   = 8000
  }

  # A deploy that never reaches a steady state is rolled back rather than left
  # half applied.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # The deploy pipeline registers new task definition revisions. Terraform owns
  # the shape of the service, not which revision is currently deployed, so an
  # apply after a deploy must not roll the service back to an older image.
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.http]

  tags = {
    Name = local.name_prefix
  }
}
