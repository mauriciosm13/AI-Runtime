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
