# Git workflow

- Conventional Commits (enforced in CI)
- Feature branches
- Pull request reviews
- Semantic Versioning

## Conventional Commits

Every commit and pull request title must follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<optional scope>): <description>

[optional body]
```

CI validates messages via `.github/workflows/conventional-commits.yml` using `.commitlintrc.yaml`.

### Allowed types

| Type | When to use |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no logic change |
| `refactor` | Code change, no feature/fix |
| `perf` | Performance improvement |
| `test` | Tests only |
| `build` | Build system or dependencies |
| `ci` | CI configuration |
| `chore` | Maintenance, tooling |
| `revert` | Reverts a previous commit |

Scope is optional (`feat(routing):`, `fix(auth):`).

### Examples

```text
feat(routing): resolve models through a static catalog
fix: release idempotency lease on policy denial
docs: document conventional commits workflow
ci: validate conventional commits in pull requests
```

### Invalid examples

```text
fix
WIP routing
updated docs
Feature: add health check
```

### Pull requests

- **Title** must follow the same format (squash merges use the PR title as the commit message).
- **Each commit** in the PR is also validated; rebase or squash before merge if older commits fail.
