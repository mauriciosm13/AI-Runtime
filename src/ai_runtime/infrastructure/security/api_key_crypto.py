"""API key secret generation and argon2id hashing.

Choice: argon2id via ``argon2-cffi``. It is a modern memory-hard password KDF
with library-managed salts, suitable for high-entropy API key secrets, and
provides a constant-time verification path for future bearer auth (#14).
"""

import secrets
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Public key format required by api-design.md.
KEY_PUBLIC_PREFIX = "airt_"
# urlsafe token length in bytes before encoding; yields ~43 chars of entropy.
_SECRET_TOKEN_BYTES = 32
# Non-secret display/lookup prefix: "airt_" + first 8 chars of the random part.
LOOKUP_PREFIX_LENGTH = len(KEY_PUBLIC_PREFIX) + 8


def derive_lookup_prefix(secret: str) -> str:
    """Return the non-secret lookup prefix for an ``airt_...`` plaintext secret."""
    return secret[:LOOKUP_PREFIX_LENGTH]


class Argon2ApiKeyHasher:
    """Generate ``airt_...`` secrets and hash/verify them with argon2id."""

    def __init__(self, password_hasher: PasswordHasher | None = None) -> None:
        # PasswordHasher defaults to argon2id with a random per-hash salt.
        self._hasher = password_hasher or PasswordHasher()

    def generate_secret(self) -> tuple[str, str]:
        """Return ``(plaintext_secret, display_prefix)`` with an ``airt_`` prefix."""
        token = secrets.token_urlsafe(_SECRET_TOKEN_BYTES)
        secret = f"{KEY_PUBLIC_PREFIX}{token}"
        prefix = derive_lookup_prefix(secret)
        return secret, prefix

    def derive_lookup_prefix(self, secret: str) -> str:
        """Return the non-secret lookup prefix derived from a plaintext secret."""
        return derive_lookup_prefix(secret)

    def hash_secret(self, secret: str) -> str:
        """Return an argon2id digest for ``secret`` (salt embedded in the digest)."""
        return self._hasher.hash(secret)

    def verify_secret(self, secret: str, secret_hash: str) -> bool:
        """Return True when ``secret`` matches ``secret_hash`` (constant-time)."""
        try:
            return self._hasher.verify(secret_hash, secret)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
