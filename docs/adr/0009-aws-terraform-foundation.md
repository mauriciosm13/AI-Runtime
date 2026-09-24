# ADR 0009: AWS network and empty Fargate shell in Terraform

## Status

Accepted

## Context

Roadmap item 27 asks for AWS infrastructure in Terraform. Item 28 adds the image pipeline, ECR, and the ECS service. Item 29 adds RDS, ElastiCache, Secrets Manager, and CloudWatch. The runtime already listens on port 8000 and exposes `GET /health`.

## Decision

1. One Terraform root module lives at `infra/terraform`. State is local. CI checks formatting and `terraform validate`; it does not apply.
2. The module creates a VPC in two availability zones, public and private subnets, and a single NAT gateway.
3. It creates an ECS cluster with Fargate capacity providers and a public HTTP load balancer whose target group expects tasks on port 8000 at `GET /health`. No service, task definition, or image repository is created.
4. TLS, RDS, ElastiCache, Secrets Manager, CloudWatch, ECR, and the deploy workflow stay on later items.

## Consequences

- Apply creates a billable NAT gateway and load balancer before any task runs.
- Private subnet egress depends on one NAT gateway.
- Item 28 can register a service on the existing cluster and target group.
- Item 29 can place data stores in the private subnets and open the app security group to them.
