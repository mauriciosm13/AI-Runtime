# A Fargate task with no log configuration discards stdout, which makes a failed
# deploy undiagnosable. Alarms, the dashboard, and their SNS topic live in
# cloudwatch.tf; this file stays scoped to the one log group.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "/ecs/${local.name_prefix}"
  }
}
