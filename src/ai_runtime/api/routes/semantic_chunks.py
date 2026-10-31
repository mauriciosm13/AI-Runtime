"""Organization-scoped semantic chunk ingestion."""

from fastapi import APIRouter
from ai_runtime.api.dependencies import AuthenticatedPrincipalDep, IngestSemanticChunkDep
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.api.schemas.semantic_chunks import CreateSemanticChunkRequest, SemanticChunkCreatedSchema
from ai_runtime.application.semantic.ingest_semantic_chunk import IngestSemanticChunkCommand

router = APIRouter(tags=["semantic_chunks"])


@router.post(
    "/semantic_chunks",
    status_code=201,
    responses={
        400: {"model": ErrorResponseSchema, "description": "Unsupported embedding model"},
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid API key"},
        422: {"model": ErrorResponseSchema, "description": "Invalid request"},
        503: {"model": ErrorResponseSchema, "description": "Embedding provider not configured"},
    },
)
async def post_semantic_chunks(
    body: CreateSemanticChunkRequest,
    principal: AuthenticatedPrincipalDep,
    use_case: IngestSemanticChunkDep,
) -> SemanticChunkCreatedSchema:
    """Embed and store organization knowledge for later RAG retrieval."""
    chunk = await use_case.execute(
        IngestSemanticChunkCommand(
            organization_id=principal.organization_id,
            content=body.content,
            embedding_model=body.embedding_model,
        )
    )
    return SemanticChunkCreatedSchema.from_domain(chunk)
