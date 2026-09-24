variable "name" {
  description = "Short product name used in resource names."
  type        = string
  default     = "ai-runtime"
}

variable "environment" {
  description = "Deployment environment. One state per environment."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment must be dev, staging, or production."
  }
}

variable "aws_region" {
  description = "AWS region for this environment."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC. Public and private subnets are carved from it."
  type        = string
  default     = "10.0.0.0/16"
}

variable "image_tag" {
  description = "Image tag the service starts from. The deploy pipeline registers later revisions by commit SHA."
  type        = string
  default     = "bootstrap"
}

variable "image_retention_count" {
  description = "Number of tagged images kept in ECR."
  type        = number
  default     = 20
}

variable "log_retention_days" {
  description = "Retention for the task log group."
  type        = number
  default     = 30
}

variable "desired_count" {
  description = "Number of API tasks to run."
  type        = number
  default     = 1
}

variable "task_cpu" {
  description = "Fargate task CPU units."
  type        = string
  default     = "512"
}

variable "task_memory" {
  description = "Fargate task memory in MiB."
  type        = string
  default     = "1024"
}

variable "github_repository" {
  description = "GitHub owner/repo allowed to assume the deploy role through OIDC."
  type        = string
  default     = "mauriciosm13/AI-Runtime"
}

variable "github_deploy_ref" {
  description = "Git ref allowed to assume the deploy role."
  type        = string
  default     = "refs/heads/main"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set to false when the account already has one."
  type        = bool
  default     = true
}

variable "health_check_grace_period_seconds" {
  description = "Time the task may take to boot before load balancer health checks can kill it."
  type        = number
  default     = 60
}

variable "container_environment" {
  description = "Non-secret environment variables for the API container."
  type        = map(string)
  default = {
    AI_RUNTIME_LOG_LEVEL = "INFO"
  }
}
