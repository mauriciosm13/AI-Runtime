"""API key secret generation and argon2id hashing.

Choice: argon2id via ``argon2-cffi``. It is a modern memory-hard password KDF
with library-managed salts, suitable for high-entropy API key secrets, and
provides a constant-time verification path for future bearer auth (#14).
"""

import secrets
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Public key format required by api-design.md.
_KEY_PUBLIC_PREFIX = "airt_"
# urlsafe token length in bytes before encoding; yields ~43 chars of entropy.
_SECRET_TOKEN_BYTES = 32
# Non-secret display/lookup prefix: "airt_" + first 8 chars of the random part.
_DISPLAY_PREFIX_LENGTH = len(_KEY_PUBLIC_PREFIX) + 8


class Argon2ApiKeyHasher:
    """Generate ``airt_...`` secrets and hash/verify them with argon2id."""

    def __init__(self, password_hasher: PasswordHasher | None = None) -> None:
        # PasswordHasher defaults to argon2id with a random per-hash salt.
        self._hasher = password_hasher or PasswordHasher()

    def generate_secret(self) -> tuple[str, str]:
        """Return ``(plaintext_secret, display_prefix)`` with an ``airt_`` prefix."""
        token = secrets.token_urlsafe(_SECRET_TOKEN_BYTES)
        secret = f"{_KEY_PUBLIC_PREFIX}{token}"
        prefix = secret[:_DISPLAY_PREFIX_LENGTH]
        return secret, prefix

    def hash_secret(self, secret: str) -> str:
        """Return an argon2id digest for ``secret`` (salt embedded in the digest)."""
        return self._hasher.hash(secret)

    def verify_secret(self, secret: str, secret_hash: str) -> bool:
        """Return True when ``secret`` matches ``secret_hash`` (constant-time)."""
        try:
            return self._hasher.verify(secret_hash, secret)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
