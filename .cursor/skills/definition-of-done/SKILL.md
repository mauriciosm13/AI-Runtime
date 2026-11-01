---
name: definition-of-done
description: Reviewer checks CONTEXT.md acceptance criteria. CI owns tests, lint, types, and format. Completion matches the AGENTS.md definition of done.
---

The reviewer checks the work against the acceptance criteria in `CONTEXT.md`.

CI still owns tests, lint, types, and format.

A task matches the definition of done in `AGENTS.md` only when:

- the code builds
- tests pass
- lint passes
- static type checking passes
- documentation is updated
- the OpenAPI specification is updated when the API changes
- the Docker build succeeds
