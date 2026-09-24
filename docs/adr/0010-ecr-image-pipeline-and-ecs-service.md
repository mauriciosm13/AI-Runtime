# ADR 0010: ECR image pipeline and ECS service

## Status

Accepted

## Context

Roadmap item 28 turns the empty Fargate shell from ADR 0009 into something that runs the runtime image. ADR 0009 left the image repository, task definition, ECS service, and deploy workflow to this item, and left RDS, ElastiCache, Secrets Manager, and CloudWatch to item 29. The runtime listens on port 8000 and `GET /health` touches neither PostgreSQL nor Redis.

## Decision

1. The same root module gains `ecr.tf`, `logs.tf`, `iam.tf`, and `ecs_service.tf`. The service attaches to the cluster, target group, private subnets, and `app` security group from ADR 0009 instead of creating new ones.
2. The ECR repository has immutable tags and scan on push. A lifecycle policy expires untagged images after one day and keeps the most recent `image_retention_count` tagged images so a rollback target always exists.
3. Images are tagged with the commit SHA only. There is no `latest` tag; immutability would reject moving it.
4. GitHub Actions authenticates through an OIDC provider and a deploy role. The trust policy pins the audience and pins `sub` to one repository and one ref (`refs/heads/main`), so other repositories and pull requests from forks cannot assume it. No AWS access key is stored in GitHub.
5. The deploy role can push to this ECR repository, update this ECS service, and pass the two task roles to `ecs-tasks.amazonaws.com`. `ecr:GetAuthorizationToken` and the task definition actions do not support resource scoping and use `*`; every other mutating action is scoped to a single resource.
6. Terraform owns the shape of the service; the pipeline owns which task definition revision runs. The service ignores changes to `task_definition` and `desired_count`, so a later `terraform apply` does not roll the service back to an older image.
7. The service has a deployment circuit breaker with rollback, and the deploy job waits for the service to stabilize, so a bad revision fails the job.
8. Trigger: every push to `main` builds and pushes an image. Deploying is `workflow_dispatch` only, because replacing what runs is not reversible the way publishing an image is. The job does not use a GitHub Environment, because that would change the OIDC `sub` claim and defeat the ref pin in decision 4.
9. This item creates one CloudWatch log group with a retention period. A Fargate task with no log configuration discards output, which would make a failed deploy undiagnosable. This is a narrow exception to ADR 0009; dashboards, alarms, and metric filters stay in item 29.
10. CI keeps running `terraform fmt` and `terraform validate` only. It never applies.

## Consequences

- A merge to `main` produces a deployable, traceable image, and a deploy or rollback is one manual workflow run against a SHA.
- Until item 29 supplies the data stores and secrets, a deployed task serves `GET /health` but cannot serve `POST /v1/responses`. The service stays stable only because the load balancer checks `/health`.
- The first `terraform apply` creates a service whose `bootstrap` image does not exist yet; tasks cannot start until the first image is pushed and deployed.
- The deploy workflow and the IAM trust policy could not be exercised against a real AWS account here; they are validated by `terraform validate` and review only.

## Alternatives considered

- Deploying automatically on every merge: rejected until the service is functional, since every merge would replace a running task with one that cannot serve requests.
- Building `latest`: rejected; it is mutable and not traceable to a commit.
- Static AWS access keys in GitHub secrets: rejected in favor of OIDC.
- Letting Terraform manage the task definition revision: rejected; each pipeline deploy would show as drift and the next apply would revert it.
