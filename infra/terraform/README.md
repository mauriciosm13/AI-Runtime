# AWS foundation

Terraform root module for one environment. It creates the network and the empty compute shell that later roadmap items attach to.

This module does not create an ECS service, a container image, a database, Redis, secrets, or CloudWatch. CI runs `terraform fmt` and `terraform validate`. It does not apply.

## What apply creates

- VPC with DNS support, two public subnets, and two private subnets
- Internet gateway and one NAT gateway in the first public subnet
- Security groups for the load balancer and future API tasks
- ECS cluster with Fargate and Fargate Spot capacity providers
- Public HTTP load balancer and an IP target group for `GET /health` on port 8000

The target group has no registered tasks, so the load balancer answers 503 until the deploy pipeline attaches a service.

NAT and the load balancer are billed while they exist, even with zero tasks.

## Deferred

| Later item | Left out of this module |
| --- | --- |
| 28 — build, ECR, ECS deploy | Image repository, task definition, ECS service, GitHub Actions deploy |
| 29 — data and operations | RDS, ElastiCache, Secrets Manager, CloudWatch |

TLS stays off until a domain and certificate exist. The listener is HTTP on port 80.

## State

State is local. Do not commit `terraform.tfstate` or `*.tfvars`. Use one working copy per environment and keep the state file outside the repository.

## Usage

```bash
cd infra/terraform
terraform init
terraform plan
```

`plan` and `apply` need AWS credentials. `validate` does not.

```bash
terraform apply
```
