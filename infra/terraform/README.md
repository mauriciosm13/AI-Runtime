# AWS foundation

Terraform root module for one environment. It creates the network, the cluster, the image repository, the service that runs the runtime image, its data stores, and its observability.

CI runs `terraform fmt` and `terraform validate`. It does not apply.

## What apply creates

- VPC with DNS support, two public subnets, and two private subnets
- Internet gateway and one NAT gateway in the first public subnet
- Security groups for the load balancer, API tasks, RDS, and ElastiCache
- ECS cluster with Fargate and Fargate Spot capacity providers
- Public HTTP load balancer and an IP target group for `GET /health` on port 8000
- ECR repository with immutable tags, scan on push, and a lifecycle policy
- Task definition, ECS service in the private subnets behind the target group, with a deployment circuit breaker and rollback
- Task execution role, an empty task role, and one CloudWatch log group
- GitHub OIDC provider and a deploy role for GitHub Actions
- Single-AZ RDS PostgreSQL instance and single-node ElastiCache Redis replication group, both in the private subnets, reachable only from the API tasks' security group
- One Secrets Manager secret holding `database_url`, `redis_url`, and the three provider API keys, injected into the task as `secrets` (never as plaintext `environment`)
- CloudWatch alarms for ECS CPU/memory, ALB 5xx and unhealthy hosts, RDS CPU/storage/memory, and ElastiCache CPU/memory, all publishing to one SNS topic, plus a dashboard aggregating the same metrics

NAT, the load balancer, RDS, and ElastiCache are billed while they exist. The service runs `desired_count` Fargate tasks.

## Secrets

Set `provider_api_keys = { openai = "...", anthropic = "...", gemini = "..." }` in a git-ignored `*.tfvars` file before applying; any key left out is stored as an empty string. `database_url` and `redis_url` are composed by this module from the RDS and ElastiCache endpoints and a generated RDS password — nothing to set for those. Rotating a key means updating the `.tfvars` file and re-applying; Terraform writes a new secret version, and the next task deployment or restart picks it up.

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

Redis traffic is unencrypted in transit (still private-subnet-only; see the tradeoff note in `elasticache.tf`). TLS on the load balancer stays off until a domain and certificate exist — the listener is HTTP on port 80.

## Deferred

| Later item | Left out of this module |
| --- | --- |
| 32 — pgvector and retrieval | pgvector extension, embeddings storage, semantic retrieval wiring |

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
