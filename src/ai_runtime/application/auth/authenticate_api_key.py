"""Use case for authenticating a bearer API key secret."""

from dataclasses import dataclass
from uuid import UUID
from ai_runtime.domain.api_key import ApiKeyStatus, InvalidApiKeyCredentialsError
from ai_runtime.domain.organization import OrganizationStatus, OrganizationSuspendedError
from ai_runtime.ports.api_key_hasher import ApiKeyHasher
from ai_runtime.ports.api_key_repository import ApiKeyRepository
from ai_runtime.ports.organization_repository import OrganizationRepository

_PUBLIC_SECRET_PREFIX = "airt_"
# airt_ + 8 chars of random part; kept in sync with Argon2ApiKeyHasher.LOOKUP_PREFIX_LENGTH.
_MIN_SECRET_LENGTH = len(_PUBLIC_SECRET_PREFIX) + 8


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Authenticated caller identity without secret material.

    Safe to attach to request context for later usage/quota work. Never includes
    plaintext secrets or ``secret_hash``.
    """

    api_key_id: UUID
    organization_id: UUID
    organization_slug: str
    api_key_prefix: str


class AuthenticateApiKey:
    """Validate a plaintext ``airt_...`` secret and resolve its principal."""

    def __init__(
        self,
        api_keys: ApiKeyRepository,
        organizations: OrganizationRepository,
        hasher: ApiKeyHasher,
    ) -> None:
        self._api_keys = api_keys
        self._organizations = organizations
        self._hasher = hasher

    async def execute(self, secret: str) -> AuthenticatedPrincipal:
        """Authenticate ``secret`` and return a non-secret principal.

        Raises ``InvalidApiKeyCredentialsError`` for any credential failure
        (malformed secret, unknown key, hash mismatch, revoked key, missing org).
        Raises ``OrganizationSuspendedError`` when the owning org is suspended.
        """
        if not secret.startswith(_PUBLIC_SECRET_PREFIX) or len(secret) < _MIN_SECRET_LENGTH:
            raise InvalidApiKeyCredentialsError("invalid api key credentials")

        prefix = self._hasher.derive_lookup_prefix(secret)
        candidates = await self._api_keys.find_by_prefix(prefix)
        matched = None
        for candidate in candidates:
            if self._hasher.verify_secret(secret, candidate.secret_hash):
                matched = candidate
                break

        if matched is None or matched.status is not ApiKeyStatus.ACTIVE:
            raise InvalidApiKeyCredentialsError("invalid api key credentials")

        organization = await self._organizations.get_by_id(matched.organization_id)
        if organization is None:
            raise InvalidApiKeyCredentialsError("invalid api key credentials")

        if organization.status is OrganizationStatus.SUSPENDED:
            raise OrganizationSuspendedError(f"organization suspended: {organization.id}")

        return AuthenticatedPrincipal(
            api_key_id=matched.id,
            organization_id=organization.id,
            organization_slug=organization.slug,
            api_key_prefix=matched.prefix,
        )
