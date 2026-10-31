# CONTEXT — HTTP semantic chunk ingestion (post–roadmap 33)

**Status:** Roadmap **33** (opt-in RAG on `POST /v1/responses`) is **delivered** (PR #19): `AugmentMessagesWithRag`, OpenAI embedding adapter, tests, and foundation docs.

**This slice:** Expose an HTTP write path so tenants can index organization-scoped semantic chunks (today only `IndexSemanticChunk` exists with no route). Completes the embeddings → storage → retrieval → RAG vertical before **roadmap 34 (MCP)** and **35–36 (LangChain examples)**.

Depends on **31** (embedding contracts), **32** (`IndexSemanticChunk`, `SearchSemanticChunks`, `semantic_chunks`), **33** (RAG read path). **Out of scope:** MCP (34), LangChain examples (35–36), JWT, tenant auth redesign, bulk/batch ingest, chunk delete/list/search HTTP APIs, SDK client methods, pgvector Terraform wiring, operator-only cross-tenant ingest.

## Objetivo

Authenticated applications index text into `semantic_chunks` for their organization via `POST /v1/semantic_chunks`. The runtime embeds content with the same embedding catalog as RAG, persists the vector, and returns chunk metadata. RAG on `POST /v1/responses` can then retrieve that content without any change to the RAG pipeline.

## Requisitos

| Fonte | Exigência |
| --- | --- |
| `README.md` (Roadmap) | First remaining open item: HTTP ingestion for semantic chunks. |
| `data-architecture.md` | Vectors beside tenant data; `organization_id` FK; ingestion was explicitly deferred until after RAG read path. |
| `requirements.md` | Chunk text is **configuration/knowledge**, not end-user chat content; store in PostgreSQL is allowed (like `prompt_templates`). Do not log chunk body on ingest. |
| Privacy / telemetry | No structured logs or audit rows containing chunk `content`; usage of embedding provider may be recorded at metadata level only if existing patterns allow (no content). |
| Auth | Same tenant model as `POST /v1/prompts`: valid `airt_...` API key → caller `organization_id`. Operator token routes stay unchanged. |

## Decisões

1. **Route:** `POST /v1/semantic_chunks` → `201 Created`. Path uses `snake_case` segment consistent with `/v1/api_keys`.

2. **Request body:**
   ```json
   { "content": "non-empty text", "embedding_model": "text-embedding-3-small" }
   ```
   - `content`: required, non-blank string (domain validation via `SemanticChunk`).
   - `embedding_model`: optional; default `text-embedding-3-small` (must match `DEFAULT_EMBEDDING_CATALOG` / `DEFAULT_EMBEDDING_DIMENSIONS`).

3. **Use case:** New `IngestSemanticChunk` in `application/semantic/` (name may vary): resolve embedding route → `EmbeddingProvider.embed` → `IndexSemanticChunk.execute`. Reuse existing ports; do not embed inside the HTTP route.

4. **Response body:** `{ "id", "organization_id", "created_at" }` — omit `content` and `embedding` from the HTTP response (clients already sent content; vectors are internal).

5. **Errors:** Mirror RAG/generation patterns: unknown model → `400` / `unsupported_model`; missing OpenAI (or catalog provider) key when embed runs → `503` / `provider_error`; invalid body → `422` / `invalid_request`; unknown org (should not happen for authenticated tenant) → propagate domain errors consistently.

6. **No pre-supplied embeddings on HTTP** in this slice (keeps one code path and dimension validation). Clients that already have vectors can keep using `IndexSemanticChunk` in tests/internal tools until a later item adds optional `embedding` in the API.

7. **Rate limiting / idempotency:** Do not add idempotency or special rate limits in this slice; generic HTTP middleware and org policies unchanged. Optional follow-up if ingest abuse becomes a concern.

8. **Tests:** Unit tests for ingest use case (fake embed + fake repo); API test with fakes or test DB (follow `test_rag_responses.py` / semantic integration patterns); assert cross-org isolation (org A chunk not visible to org B search).

9. **Docs:** Add row to `api-design.md` route map; extend `architecture.md` and `data-architecture.md` (ingestion no longer “later”); update `README.md` roadmap “Still open” line when done.

10. **ADR:** Small **ADR 0012** (or next number) only if ingest auth or persistence semantics need a recorded decision; otherwise foundation doc updates suffice.

## Arquivos (touch esperado)

| Área | Paths |
| --- | --- |
| Application | `application/semantic/ingest_semantic_chunk.py` (new), wire in `application/semantic/__init__.py` if present |
| API | `api/routes/semantic_chunks.py` (new), `api/schemas/semantic_chunks.py` (new), `api/dependencies.py`, `api/router` registration (main app) |
| Tests | `tests/application/semantic/test_ingest_semantic_chunk.py`, `tests/api/test_semantic_chunks.py` |
| Docs | `docs/foundation/api-design.md`, `docs/architecture.md`, `docs/foundation/data-architecture.md`, `README.md` |
| Optional | `docs/adr/0012-semantic-chunk-http-ingestion.md` |

## Critérios de aceitação

- [ ] `POST /v1/semantic_chunks` with tenant API key stores a chunk for that key’s `organization_id` only.
- [ ] Subsequent `POST /v1/responses` with `rag.enabled: true` can retrieve ingested content for the same organization.
- [ ] Chunk `content` does not appear in application logs for the ingest request path.
- [ ] Invalid or unknown `embedding_model` → `400` / `unsupported_model`.
- [ ] Unconfigured embedding provider → `503` / `provider_error` on ingest (same as RAG).
- [ ] pytest, ruff, mypy CI green; OpenAPI reflects the new route.

## Referência (implementação existente)

- `application/semantic/index_semantic_chunk.py` — persist after org check
- `application/rag/augment_messages_with_rag.py` — embedding + search pattern
- `domain/embedding_routing.py`, `providers/openai/embedding.py`
- `api/routes/prompts.py` — tenant-scoped POST pattern
- `tests/application/semantic/test_index_and_search.py`, `tests/api/test_rag_responses.py`

---

## Delegação

### Implementer — subtasks (order)

| ID | Title | Purpose | Acceptance |
| --- | --- | --- | --- |
| I1 | `IngestSemanticChunk` use case | Embed + index in one application operation | Unit tests with fakes; org-not-found handled |
| I2 | API schema + route | Thin HTTP layer, DI wiring | `201` response shape; auth matches prompts |
| I3 | Integration tests | Prove ingest → RAG retrieval E2E in test harness | Cross-org isolation test |
| I4 | Documentation | Route map + architecture + README | Ingestion marked implemented; “Still open” trimmed |

### Reviewer — checklist

| ID | Focus |
| --- | --- |
| R1 | Clean Architecture: no business rules in route; no provider calls from API layer |
| R2 | Tenant isolation: `organization_id` only from authenticated principal, never from request body |
| R3 | Privacy: no chunk content in logs, metrics labels, or audit metadata |
| R4 | Consistency: error codes and embedding catalog aligned with RAG on `POST /v1/responses` |
| R5 | Scope: no MCP, SDK, batch APIs, or Terraform in the diff |

### Explorer (optional, readonly)

- Confirm no existing `/v1/semantic*` routes or duplicate ingest use cases before I2.
- After implementation, verify OpenAPI and `api-design.md` route table match.

---

## Próximo depois deste slice

| Ordem | Item | Notas |
| --- | --- | --- |
| 1 | **Roadmap 34 — MCP tool servers** | ADR 0005; builds on tool-calling contract (23). |
| 2 | **Roadmap 35–36 — LangChain / multi-agent examples** | Client examples, not core runtime. |
| Paralelo / infra | pgvector on RDS Terraform | README gap; not blocking HTTP ingest on Compose. |
