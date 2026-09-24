# AWS foundation

Terraform root module for one environment. It creates the network, the cluster, the image repository, and the service that runs the runtime image.

This module does not create a database, Redis, secrets, or CloudWatch dashboards and alarms. CI runs `terraform fmt` and `terraform validate`. It does not apply.

## What apply creates

- VPC with DNS support, two public subnets, and two private subnets
- Internet gateway and one NAT gateway in the first public subnet
- Security groups for the load balancer and API tasks
- ECS cluster with Fargate and Fargate Spot capacity providers
- Public HTTP load balancer and an IP target group for `GET /health` on port 8000
- ECR repository with immutable tags, scan on push, and a lifecycle policy
- Task definition, ECS service in the private subnets behind the target group, with a deployment circuit breaker and rollback
- Task execution role, an empty task role, and one CloudWatch log group
- GitHub OIDC provider and a deploy role for GitHub Actions

NAT and the load balancer are billed while they exist. The service runs `desired_count` Fargate tasks.

## Deploying

Terraform owns the shape of the service. The pipeline owns which task definition revision runs: the service ignores changes to `task_definition` and `desired_count`, so an apply after a deploy does not roll the image back.

`.github/workflows/deploy.yml` builds an image on every push to `main` and pushes it to ECR tagged with the commit SHA. It deploys only when run manually (`workflow_dispatch`). It authenticates through OIDC; the deploy role trusts one repository and one ref (`github_repository`, `github_deploy_ref`). No AWS access key is stored in GitHub.

Set these repository variables from the outputs:

| Variable | Output |
| --- | --- |
| `AWS_REGION` | `aws_region` input |
| `AWS_DEPLOY_ROLE_ARN` | `github_deploy_role_arn` |
| `ECR_REPOSITORY` | last path segment of `ecr_repository_url` |
| `ECS_CLUSTER` | `ecs_cluster_name` |
| `ECS_SERVICE` | `ecs_service_name` |
| `ECS_TASK_FAMILY` | `task_definition_family` |

First deploy: `terraform apply` creates a service whose `bootstrap` image does not exist yet, so tasks cannot start. Push to `main` to publish an image, then run the Deploy workflow manually. Set `create_github_oidc_provider = false` when the account already has a GitHub OIDC provider.

## Limitation

There is no database, Redis, or provider API key yet. A deployed task serves `GET /health`, which is what keeps it in service, but `POST /v1/responses` fails until the data and operations item adds them.

## Deferred

| Later item | Left out of this module |
| --- | --- |
| 29 — data and operations | RDS, ElastiCache, Secrets Manager, CloudWatch dashboards and alarms |

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
