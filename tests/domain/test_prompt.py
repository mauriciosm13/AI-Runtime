"""Prompt template domain tests."""

from datetime import UTC, datetime
from uuid import uuid4
import pytest
from ai_runtime.domain.context import ContextPolicy
from ai_runtime.domain.generation import DomainValidationError, MessageRole
from ai_runtime.domain.prompt import PromptMessageTemplate, PromptReference, PromptTemplate


def _template(*contents: str, role: MessageRole = MessageRole.USER) -> PromptTemplate:
    return PromptTemplate(
        id=uuid4(),
        organization_id=uuid4(),
        name="support.reply",
        version=1,
        messages=tuple(PromptMessageTemplate(role=role, content=content) for content in contents),
        created_at=datetime.now(UTC),
    )


def test_render_substitutes_variables_in_every_message() -> None:
    template = PromptTemplate(
        id=uuid4(),
        organization_id=uuid4(),
        name="greet",
        version=2,
        messages=(
            PromptMessageTemplate(role=MessageRole.SYSTEM, content="You help {{ company }}."),
            PromptMessageTemplate(role=MessageRole.USER, content="Hi, I am {{name}} from {{company}}."),
        ),
        created_at=datetime.now(UTC),
    )
    rendered = template.render({"company": "Acme", "name": "Ana"})
    assert [(item.role, item.content) for item in rendered] == [
        (MessageRole.SYSTEM, "You help Acme."),
        (MessageRole.USER, "Hi, I am Ana from Acme."),
    ]
    assert template.placeholders == {"company", "name"}


def test_render_does_not_expand_placeholders_inside_values() -> None:
    rendered = _template("Say: {{text}}").render({"text": "{{text}} and {{other}}"})
    assert rendered[0].content == "Say: {{text}} and {{other}}"


def test_render_rejects_missing_variable() -> None:
    with pytest.raises(DomainValidationError, match="missing prompt variables: b"):
        _template("{{a}} {{b}}").render({"a": "x"})


def test_render_rejects_unknown_variable() -> None:
    with pytest.raises(DomainValidationError, match="unknown prompt variables: extra"):
        _template("{{a}}").render({"a": "x", "extra": "y"})


def test_template_without_placeholders_renders_with_no_variables() -> None:
    assert _template("plain").render({})[0].content == "plain"


def test_message_template_rejects_tool_role_and_blank_content() -> None:
    with pytest.raises(DomainValidationError):
        PromptMessageTemplate(role=MessageRole.TOOL, content="x")
    with pytest.raises(DomainValidationError):
        PromptMessageTemplate(role=MessageRole.USER, content="   ")


@pytest.mark.parametrize("name", ["", "has space", "a/b", "x" * 65])
def test_template_rejects_invalid_names(name: str) -> None:
    with pytest.raises(DomainValidationError):
        PromptTemplate(
            id=uuid4(),
            organization_id=uuid4(),
            name=name,
            version=1,
            messages=(PromptMessageTemplate(role=MessageRole.USER, content="x"),),
            created_at=datetime.now(UTC),
        )


def test_reference_and_policy_validate_bounds() -> None:
    with pytest.raises(DomainValidationError):
        PromptReference(name="ok", variables={}, version=0)
    with pytest.raises(DomainValidationError):
        ContextPolicy(max_input_tokens=0)
