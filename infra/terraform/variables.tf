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

variable "provider_api_keys" {
  description = "OpenAI, Anthropic, and Gemini API keys, stored in Secrets Manager. Keys: openai, anthropic, gemini. Missing keys are stored as an empty string."
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "db_name" {
  description = "Name of the application database created on the RDS instance."
  type        = string
  default     = "ai_runtime"
}

variable "db_username" {
  description = "Master username for the RDS instance."
  type        = string
  default     = "ai_runtime"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  description = "Allocated storage for the RDS instance, in GiB."
  type        = number
  default     = 20
}

variable "db_engine_version" {
  description = "PostgreSQL major/minor version for RDS."
  type        = string
  default     = "16.4"
}

variable "db_backup_retention_days" {
  description = "Number of days RDS keeps automated backups."
  type        = number
  default     = 7
}

variable "db_multi_az" {
  description = "Whether the RDS instance runs Multi-AZ."
  type        = bool
  default     = false
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "redis_engine_version" {
  description = "Redis engine version for ElastiCache."
  type        = string
  default     = "7.1"
}

variable "alarm_email" {
  description = "Email address subscribed to the CloudWatch alarm SNS topic. Empty string creates no subscription."
  type        = string
  default     = ""
}
