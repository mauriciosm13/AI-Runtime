"""Unit tests for RAG domain helpers."""

import pytest
from ai_runtime.domain.generation import Message, MessageRole
from ai_runtime.domain.rag import RagPolicy, format_retrieved_context, prepend_retrieved_context, resolve_rag_query


def test_resolve_rag_query_uses_last_user_message() -> None:
    messages = (
        Message(role=MessageRole.USER, content="first"),
        Message(role=MessageRole.ASSISTANT, content="ok"),
        Message(role=MessageRole.USER, content="  second question  "),
    )
    assert resolve_rag_query(messages, override=None) == "second question"


def test_format_retrieved_context_numbers_chunks() -> None:
    body = format_retrieved_context(["alpha", "beta"])
    assert body.startswith("Retrieved context (organization knowledge):")
    assert "1. alpha" in body
    assert "2. beta" in body


def test_prepend_retrieved_context_noop_on_empty() -> None:
    messages = (Message(role=MessageRole.USER, content="Hi"),)
    assert prepend_retrieved_context(messages, []) == messages


def test_rag_policy_rejects_top_k_above_max() -> None:
    with pytest.raises(Exception):
        RagPolicy(enabled=True, top_k=21)
