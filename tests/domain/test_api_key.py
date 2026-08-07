"""Unit tests for API key domain contracts."""

from datetime import UTC, datetime
from uuid import uuid4
import pytest
from ai_runtime.domain.api_key import ApiKey, ApiKeyAlreadyRevokedError, ApiKeyStatus
from ai_runtime.domain.generation import DomainValidationError


def _aware_now() -> datetime:
    return datetime.now(UTC)


def _active_key(**overrides: object) -> ApiKey:
    now = _aware_now()
    values: dict[str, object] = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "name": "default",
        "prefix": "airt_abcdefgh",
        "secret_hash": "$argon2id$v=19$m=65536,t=3,p=4$testhash",
        "status": ApiKeyStatus.ACTIVE,
        "created_at": now,
        "revoked_at": None,
        "updated_at": now,
    }
    values.update(overrides)
    return ApiKey(**values)  # type: ignore[arg-type]


def test_valid_api_key_constructs() -> None:
    """A valid ApiKey accepts organization, prefix, hash, and timestamps."""
    key = _active_key(name=None)
    assert key.name is None
    assert key.status is ApiKeyStatus.ACTIVE
    assert key.revoked_at is None


def test_to_metadata_excludes_secret_hash() -> None:
    """Metadata projection never includes secret_hash."""
    key = _active_key()
    metadata = key.to_metadata()
    assert metadata.id == key.id
    assert metadata.prefix == key.prefix
    assert not hasattr(metadata, "secret_hash")
    assert "secret_hash" not in metadata.__dataclass_fields__


def test_rejects_blank_name_when_provided() -> None:
    """Optional name must not be blank when present."""
    with pytest.raises(DomainValidationError, match="name"):
        _active_key(name="   ")


def test_rejects_blank_prefix() -> None:
    """Prefix must not be empty or blank."""
    with pytest.raises(DomainValidationError, match="prefix"):
        _active_key(prefix=" ")


def test_rejects_blank_secret_hash() -> None:
    """secret_hash must not be empty or blank."""
    with pytest.raises(DomainValidationError, match="secret_hash"):
        _active_key(secret_hash="")


def test_rejects_naive_timestamps() -> None:
    """created_at and updated_at must be timezone-aware."""
    naive = datetime(2026, 1, 1, 0, 0, 0)
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        _active_key(created_at=naive, updated_at=naive)


def test_revoked_key_requires_revoked_at() -> None:
    """Revoked status without revoked_at is invalid."""
    with pytest.raises(DomainValidationError, match="revoked_at"):
        _active_key(status=ApiKeyStatus.REVOKED, revoked_at=None)


def test_active_key_rejects_revoked_at() -> None:
    """Active status with revoked_at set is invalid."""
    with pytest.raises(DomainValidationError, match="active keys"):
        _active_key(revoked_at=_aware_now())


def test_revoke_marks_status_and_timestamp() -> None:
    """revoke() returns a revoked copy with revoked_at and updated_at."""
    key = _active_key()
    at = _aware_now()
    revoked = key.revoke(at)
    assert revoked.status is ApiKeyStatus.REVOKED
    assert revoked.revoked_at == at
    assert revoked.updated_at == at
    assert key.status is ApiKeyStatus.ACTIVE


def test_revoke_already_revoked_raises() -> None:
    """Double-revoke raises ApiKeyAlreadyRevokedError (explicit policy)."""
    at = _aware_now()
    revoked = _active_key(status=ApiKeyStatus.REVOKED, revoked_at=at, updated_at=at)
    with pytest.raises(ApiKeyAlreadyRevokedError, match="already revoked"):
        revoked.revoke(_aware_now())


def test_api_key_status_values() -> None:
    """ApiKeyStatus exposes the supported lifecycle values."""
    assert ApiKeyStatus.ACTIVE.value == "active"
    assert ApiKeyStatus.REVOKED.value == "revoked"
