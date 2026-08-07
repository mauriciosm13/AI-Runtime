"""Domain errors for request idempotency."""


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is already in progress for the organization."""

    def __init__(self) -> None:
        super().__init__("A request with this Idempotency-Key is already in progress.")
