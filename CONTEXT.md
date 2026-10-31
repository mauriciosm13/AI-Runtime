# CONTEXT — RAG on POST /v1/responses (roadmap 33)

Depends on **31** (`EmbeddingProvider`), **32** (`SearchSemanticChunks`, `semantic_chunks`), **25** (context builder, prompts). **Out of scope:** MCP (34), LangChain examples (35–36), HTTP chunk ingestion (operator API), JWT, changes to tenant auth design.

## Objetivo

When a client opts in on `POST /v1/responses`, embed a query, retrieve organization-scoped semantic chunks from pgvector, inject them into the message list, then run the existing generation path (policy, provider, usage, cache, idempotency unchanged in behavior except augmented messages).

## Requisitos

| Fonte | Exigência |
| --- | --- |
| `roadmap.md` item 33 | RAG: buscar contexto e injetar em `POST /v1/responses`. |
| `data-architecture.md` | Vectors beside tenant data; retrieval scoped by `organization_id`. |
| `requirements.md` | No default persistence of end-user prompt/response; injected context is ephemeral for the request (not stored). |
| Privacy | Do not log retrieved chunk text or query; audit unchanged (no content). |

## Decisões

1. **Opt-in API field** `rag` on `CreateResponseRequest`:
   ```json
   { "enabled": true, "query": "optional override", "top_k": 5, "embedding_model": "text-embedding-3-small" }
   ```
   - Omitted or `enabled: false` → no retrieval (backward compatible).
   - Default **query**: last non-empty `user` message in the resolved message list (after prompt render).
   - Default **top_k**: 5; max 20.
   - Default **embedding_model**: `text-embedding-3-small` (1536 dims, matches `DEFAULT_EMBEDDING_DIMENSIONS`).

2. **Injection shape:** Prepend one `system` message:
   `Retrieved context (organization knowledge):\n\n1. …\n2. …`
   Then existing messages (including other system messages). Empty retrieval → no extra message.

3. **Pipeline order** in `post_responses`: resolve prompt → **RAG augment** → `BuildContext` (when `needs_context_check`, now also true when `rag.enabled`) → `CreateResponse`.

4. **Embedding execution:** Minimal `OpenAIEmbeddingProvider` (`providers/openai/embedding.py`) implementing `EmbeddingProvider` via OpenAI `/v1/embeddings`. Static catalog `DEFAULT_EMBEDDING_CATALOG` in `domain/embedding_routing.py` (model → provider). Missing OpenAI key → `503` / `provider_error` when RAG runs.

5. **Use case:** `AugmentMessagesWithRag` in `application/rag/` — inputs: `organization_id`, `messages`, `RagPolicy`; uses embed + `SearchSemanticChunks`; returns new message tuple.

6. **Streaming / cache / tools:** `rag` + `stream: true` **allowed** (retrieval completes before stream). `rag` + `cache: true` allowed (cache key reflects augmented messages). `rag` incompatible with nothing extra beyond existing prompt/messages rules.

7. **Tests:** Unit tests for augment (fakes); API test with fakes for embed+search; OpenAI embedding adapter tests with httpx mock (mirror chat adapter tests).

8. **Docs:** `api-design.md`, `architecture.md`, README roadmap line; mark roadmap **33** `[x]` in workspace `roadmap.md`.

## Arquivos (touch esperado)

| Área | Paths |
| --- | --- |
| Domain | `domain/rag.py`, `domain/embedding_routing.py` |
| Application | `application/rag/augment_messages_with_rag.py` |
| Provider | `providers/openai/embedding.py` |
| API | `api/schemas/responses.py`, `api/routes/responses.py`, `api/dependencies.py` |
| Tests | `tests/application/rag/`, `tests/providers/openai/test_openai_embedding.py`, `tests/api/test_rag_responses.py` |
| Docs | `docs/foundation/api-design.md`, `docs/architecture.md`, `README.md` |

## Critérios de aceitação

- [ ] `rag.enabled: true` retrieves only within caller `organization_id` and injects context before generation.
- [ ] Without `rag`, behavior identical to pre-33.
- [ ] Embedding model not in catalog → `400` / `unsupported_model` (or dedicated code if already present).
- [ ] Tests pass; ruff/mypy/pytest CI green.
- [ ] No logging of chunk content or query text.

## Referência

- `application/semantic/search_semantic_chunks.py`
- `api/routes/responses.py` prompt + context flow
- `providers/openai/adapter.py` httpx test patterns
