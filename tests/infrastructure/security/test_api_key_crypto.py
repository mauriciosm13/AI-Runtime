"""Unit tests for argon2id API key hashing and secret generation."""

from ai_runtime.infrastructure.security.api_key_crypto import Argon2ApiKeyHasher
from ai_runtime.ports.api_key_hasher import ApiKeyHasher


def test_hasher_satisfies_api_key_hasher_contract() -> None:
    """Argon2ApiKeyHasher is accepted as ApiKeyHasher."""
    hasher: ApiKeyHasher = Argon2ApiKeyHasher()
    assert isinstance(hasher, ApiKeyHasher)


def test_generate_secret_uses_airt_prefix() -> None:
    """Generated secrets use the public airt_ prefix and a shorter display prefix."""
    hasher = Argon2ApiKeyHasher()
    secret, prefix = hasher.generate_secret()
    assert secret.startswith("airt_")
    assert prefix.startswith("airt_")
    assert secret.startswith(prefix)
    assert len(prefix) < len(secret)
    assert len(prefix) == len("airt_") + 8


def test_verify_accepts_original_secret() -> None:
    """verify_secret returns True for the original plaintext."""
    hasher = Argon2ApiKeyHasher()
    secret, _prefix = hasher.generate_secret()
    digest = hasher.hash_secret(secret)
    assert digest.startswith("$argon2id$")
    assert hasher.verify_secret(secret, digest) is True


def test_verify_rejects_wrong_secret() -> None:
    """verify_secret returns False for a tampered or unrelated secret."""
    hasher = Argon2ApiKeyHasher()
    secret, _prefix = hasher.generate_secret()
    digest = hasher.hash_secret(secret)
    assert hasher.verify_secret(secret + "x", digest) is False
    assert hasher.verify_secret("airt_not-the-real-secret", digest) is False


def test_verify_rejects_invalid_hash() -> None:
    """verify_secret returns False for malformed hash strings."""
    hasher = Argon2ApiKeyHasher()
    assert hasher.verify_secret("airt_anything", "not-a-valid-argon2-hash") is False


def test_hash_is_not_plaintext() -> None:
    """The stored digest must not equal or embed the plaintext secret."""
    hasher = Argon2ApiKeyHasher()
    secret, _prefix = hasher.generate_secret()
    digest = hasher.hash_secret(secret)
    assert digest != secret
    assert secret not in digest
