"""Unit tests for organization domain contracts."""

from datetime import UTC, datetime
from uuid import uuid4
import pytest
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.domain.organization import Organization, OrganizationStatus


def _aware_now() -> datetime:
    return datetime.now(UTC)


def test_valid_organization_constructs() -> None:
    """A valid Organization accepts name, slug, status, and timestamps."""
    org_id = uuid4()
    created = _aware_now()
    organization = Organization(
        id=org_id,
        name="Acme Corp",
        slug="acme-corp",
        status=OrganizationStatus.ACTIVE,
        created_at=created,
        updated_at=created,
    )
    assert organization.id == org_id
    assert organization.name == "Acme Corp"
    assert organization.slug == "acme-corp"
    assert organization.status is OrganizationStatus.ACTIVE


def test_rejects_blank_name() -> None:
    """Organization name must not be empty or blank."""
    now = _aware_now()
    with pytest.raises(DomainValidationError, match="name"):
        Organization(
            id=uuid4(),
            name="   ",
            slug="acme",
            status=OrganizationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )


def test_rejects_blank_slug() -> None:
    """Organization slug must not be empty or blank."""
    now = _aware_now()
    with pytest.raises(DomainValidationError, match="slug"):
        Organization(
            id=uuid4(),
            name="Acme",
            slug=" ",
            status=OrganizationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )


@pytest.mark.parametrize("slug", ["Acme", "acme_corp", "acme.corp", "acme!", ""])
def test_rejects_invalid_slug(slug: str) -> None:
    """Slug must be lowercase letters, digits, and hyphens only."""
    now = _aware_now()
    with pytest.raises(DomainValidationError, match="slug"):
        Organization(
            id=uuid4(),
            name="Acme",
            slug=slug,
            status=OrganizationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )


def test_accepts_slug_with_hyphens() -> None:
    """Hyphenated lowercase slugs are valid."""
    now = _aware_now()
    organization = Organization(
        id=uuid4(),
        name="Acme",
        slug="acme-corp-1",
        status=OrganizationStatus.SUSPENDED,
        created_at=now,
        updated_at=now,
    )
    assert organization.slug == "acme-corp-1"
    assert organization.status is OrganizationStatus.SUSPENDED


def test_rejects_naive_timestamps() -> None:
    """created_at and updated_at must be timezone-aware."""
    naive = datetime(2026, 1, 1, 0, 0, 0)
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        Organization(
            id=uuid4(),
            name="Acme",
            slug="acme",
            status=OrganizationStatus.ACTIVE,
            created_at=naive,
            updated_at=naive,
        )


def test_organization_status_values() -> None:
    """OrganizationStatus exposes the supported lifecycle values."""
    assert OrganizationStatus.ACTIVE.value == "active"
    assert OrganizationStatus.SUSPENDED.value == "suspended"
