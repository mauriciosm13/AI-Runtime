"""Port for generating and hashing API key secrets."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ApiKeyHasher(Protocol):
    """Generate ``airt_...`` secrets and hash/verify them with a password KDF.

    Implementations live in infrastructure (argon2id). Application code depends
    only on this port so domain/application stay free of crypto libraries.
    """

    def generate_secret(self) -> tuple[str, str]:
        """Return ``(plaintext_secret, display_prefix)``.

        The plaintext secret is shown once at creation and never persisted.
        The prefix is a non-secret fragment used for display and lookup.
        """
        ...

    def hash_secret(self, secret: str) -> str:
        """Return a salted KDF digest for ``secret`` (never reversible)."""
        ...

    def verify_secret(self, secret: str, secret_hash: str) -> bool:
        """Return True when ``secret`` matches ``secret_hash`` (constant-time).

        This checks cryptographic match only. Callers that authorize requests
        must also enforce key status (e.g. reject revoked keys).
        """
        ...
