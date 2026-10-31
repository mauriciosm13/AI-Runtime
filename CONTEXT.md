# CONTEXT — Operator HTTP for organizations & API keys

Roadmap slice: README **Current status** bullet *authentication, organizations, and API keys* — expose planned **operator-only** admin routes. **Out of scope:** redo tenant Bearer `airt_...` auth, organization domain/persistence, argon2id hashing, organization policies/quotas, JWT (not in repo requirements).

## Objetivo

Expor em HTTP os use cases já existentes de organizações e API keys, com autorização **operator-only** separada da autenticação de aplicação (`AuthenticateApiKey`). Fechar o gap citado em `docs/architecture.md`: use cases existem, rotas admin não.

Atender `requirements.md`: operadores podem **criar, listar, revogar e rotacionar** API keys (rotate não tem rota na tabela de `api-design.md`; ver decisões).

## Requisitos (fontes do repositório)

| Fonte | Exigência |
| --- | --- |
| `docs/foundation/requirements.md` | Identificar caller por API key; key pertence a uma org; operadores: create, list, revoke, **rotate** keys. |
| `docs/foundation/api-design.md` | Rotas Planned operator-only: `POST/GET /v1/organizations`, `POST/GET/DELETE /v1/api_keys`. Auth admin “will be designed with the authentication feature”; **não** assumir que todo portador de API key de tenant acessa admin. |
| `docs/architecture.md` | `CreateOrganization`, `GetOrganization`, `CreateApiKey`, `RevokeApiKey`, `ListApiKeysForOrganization`, `AuthenticateApiKey` — **não expostos** (operator routes = later work). |
| `README.md` | JWT **não** faz parte do desenho atual de auth. |

## Decisões

1. **Sem JWT.** Credencial de operador = segredo estático em env `AI_RUNTIME_OPERATOR_TOKEN` (Settings `operator_token`). Comparar com `secrets.compare_digest`. Header igual ao resto: `Authorization: Bearer <token>`. Token **não** é validado via `AuthenticateApiKey` / prefixo `airt_`.
2. **403 para tenant keys em rotas operator.** Se o Bearer for válido como API key de aplicação mas não for o operator token → `403` / `forbidden` (falta entitlement admin), não reutilizar fluxo tenant.
3. **401** apenas para Authorization ausente, malformado, ou operator token incorreto quando `operator_token` está configurado. Se `operator_token` estiver **vazio**, rotas operator respondem `503` / `provider_error` ou novo código documentado — preferência: **`503`** com mensagem segura “Operator API is not configured.” (bootstrap explícito).
4. **Rotate:** `requirements.md` exige rotate; `api-design.md` só lista DELETE revoke. Adicionar use case `RotateApiKey` (revoga key ativa + cria nova na mesma org, preservando `name` opcional) e rota **`POST /v1/api_keys/{key_id}/rotate`** (additive `/v1`). Atualizar linha de status em `api-design.md`. Audit: `api_key.rotated` (ou reutilizar revoked + created — preferir evento único `api_key.rotated` com metadata `previous_key_id`).
5. **Contratos HTTP** (snake_case, envelope de erro existente):
   - `POST /v1/organizations` body `{ "name", "slug" }` → `201` org JSON (`id`, `name`, `slug`, `status`, `created_at`, `updated_at`).
   - `GET /v1/organizations/{organization_id}` → `200` mesmo shape ou `404`.
   - `POST /v1/api_keys` body `{ "organization_id", "name"? }` → `201` metadata + **`secret`** (one-time, igual use case).
   - `GET /v1/api_keys?organization_id=<uuid>` → `200` `{ "api_keys": [...] }` metadata only.
   - `DELETE /v1/api_keys/{key_id}` → `200` metadata revogada ou `404` / `409` se já revogada (`ApiKeyAlreadyRevokedError` → `409` / `conflict`).
   - `POST /v1/api_keys/{key_id}/rotate` → `201` novo metadata + `secret`; key anterior revogada.
6. **Camadas:** rotas só orquestram; mapear domain errors em `exception_handlers.py` (`OrganizationNotFoundError`, `ApiKeyNotFoundError`, `OrganizationSlugConflictError`, `ApiKeyAlreadyRevokedError`) onde faltarem.
7. **Docs/README:** marcar rotas como Implemented em `api-design.md`; parágrafo README “operator routes not implemented” → implemented (sem SDK operator em ADR 0011 — opcional nota, não expandir SDK neste slice).
8. **Testes:** `tests/api/test_operator_*.py` (ou similar) com `create_app` + operator token injetado; provar tenant `airt_` **não** acessa admin; happy paths create org/key/list/revoke/rotate.

## Arquivos (touch esperado)

| Área | Paths |
| --- | --- |
| Settings | `src/ai_runtime/config/settings.py`, `.env.example` |
| Auth boundary | `src/ai_runtime/api/dependencies.py` (`require_operator`) |
| Routes | `src/ai_runtime/api/routes/organizations.py`, `api/routes/api_keys.py`, `api/app.py` |
| Schemas | `src/ai_runtime/api/schemas/organizations.py`, `api/schemas/api_keys.py` |
| Use case | `src/ai_runtime/application/api_keys/rotate_api_key.py` + testes em `tests/application/api_keys/` |
| Errors | `src/ai_runtime/api/exception_handlers.py` |
| Docs | `docs/foundation/api-design.md`, `docs/architecture.md`, `README.md` |
| Tests API | `tests/api/test_operator_routes.py` |

## Critérios de aceitação

- [ ] Cinco rotas de `api-design.md` (org create/get, api key create/list/delete) expostas e protegidas por operator token.
- [ ] Rotate disponível via HTTP alinhado a `requirements.md`.
- [ ] API key de tenant autenticada **não** chama rotas operator (403).
- [ ] Segredos `airt_` só no create/rotate response; list/get nunca retornam hash ou secret.
- [ ] Testes API + use case rotate passam; `ruff`/pytest existentes verdes.
- [ ] Sem JWT, sem mudança em argon2id/policies/fluxo `POST /v1/responses`.

## Referência rápida (já implementado — não refazer)

- `application/organizations/create_organization.py`, `get_organization.py`
- `application/api_keys/create_api_key.py`, `revoke_api_key.py`, `list_api_keys.py`
- `application/auth/authenticate_api_key.py`
- Padrão de rota: `api/routes/prompts.py` + DI em `dependencies.py`
