# A Fargate task with no log configuration discards stdout, which makes a failed
# deploy undiagnosable. This is the only CloudWatch resource in this slice;
# dashboards, alarms, and metric filters belong to the data and operations item.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "/ecs/${local.name_prefix}"
  }
}
