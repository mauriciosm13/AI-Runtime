"""Shared helpers for PostgreSQL integration tests."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from ai_runtime.infrastructure.db.base import Base


async def recreate_schema(connection: AsyncConnection) -> None:
    """Drop and recreate all ORM tables, enabling pgvector when required."""
    await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)
