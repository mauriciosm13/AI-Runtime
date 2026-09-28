locals {
  # Exact URL shapes ai_runtime.config.settings.Settings validates.
  database_url = "postgresql+asyncpg://${var.db_username}:${random_password.db.result}@${aws_db_instance.this.address}:${aws_db_instance.this.port}/${var.db_name}"
  redis_url    = "redis://${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"

  app_secret_payload = {
    database_url      = local.database_url
    redis_url         = local.redis_url
    openai_api_key    = lookup(var.provider_api_keys, "openai", "")
    anthropic_api_key = lookup(var.provider_api_keys, "anthropic", "")
    gemini_api_key    = lookup(var.provider_api_keys, "gemini", "")
  }
}

resource "aws_secretsmanager_secret" "app" {
  name        = "${local.name_prefix}-app"
  description = "Database URL, Redis URL, and provider API keys for the API task. One key per Settings field."

  tags = {
    Name = "${local.name_prefix}-app"
  }
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(local.app_secret_payload)
}

data "aws_iam_policy_document" "task_execution_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.app.arn]
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name   = "secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets.json
}
