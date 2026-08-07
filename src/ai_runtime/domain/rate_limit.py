"""Domain errors for platform rate limiting."""


class RateLimitExceededError(Exception):
    """Raised when an organization exceeds its request rate limit."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Rate limit exceeded.")
