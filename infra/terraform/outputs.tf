output "vpc_id" {
  description = "VPC that later data stores and tasks join."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Subnets for the load balancer."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Subnets for future tasks and data stores."
  value       = aws_subnet.private[*].id
}

output "ecs_cluster_name" {
  description = "Fargate cluster. No service is registered yet."
  value       = aws_ecs_cluster.this.name
}

output "ecs_cluster_arn" {
  description = "ARN of the Fargate cluster."
  value       = aws_ecs_cluster.this.arn
}

output "alb_dns_name" {
  description = "Public DNS name of the load balancer."
  value       = aws_lb.this.dns_name
}

output "alb_security_group_id" {
  description = "Security group attached to the load balancer."
  value       = aws_security_group.alb.id
}

output "app_security_group_id" {
  description = "Security group for future API tasks."
  value       = aws_security_group.app.id
}

output "target_group_arn" {
  description = "IP target group on port 8000. Item 28 registers tasks here."
  value       = aws_lb_target_group.api.arn
}

output "ecr_repository_url" {
  description = "Image repository the deploy pipeline pushes to."
  value       = aws_ecr_repository.api.repository_url
}

output "ecs_service_name" {
  description = "API service the deploy pipeline updates."
  value       = aws_ecs_service.api.name
}

output "task_definition_family" {
  description = "Task definition family the deploy pipeline registers revisions in."
  value       = aws_ecs_task_definition.api.family
}

output "github_deploy_role_arn" {
  description = "Role GitHub Actions assumes through OIDC."
  value       = aws_iam_role.github_deploy.arn
}

output "log_group_name" {
  description = "Log group that receives container output."
  value       = aws_cloudwatch_log_group.api.name
}
