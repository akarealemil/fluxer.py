from __future__ import annotations

from typing import Any


class FluxerException(Exception):
    """Base exception for all fluxer.py errors."""


# =============================================================================
# HTTP Errors
# =============================================================================


class HTTPException(FluxerException):
    """Raised when an HTTP request to the Fluxer API fails."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        errors: list[dict[str, Any]] | None = None,
    ):
        self.status = status
        self.code = code
        self.message = message
        self.errors = errors or []
        super().__init__(f"{status} {code}: {message}")


class BadRequest(HTTPException):
    """400 Bad Request — invalid input."""


class Unauthorized(HTTPException):
    """401 Unauthorized — bad or missing token."""


class Forbidden(HTTPException):
    """403 Forbidden — missing permissions."""


class NotFound(HTTPException):
    """404 Not Found — resource doesn't exist."""


class RateLimited(HTTPException):
    """429 Too Many Requests — slow down."""

    def __init__(self, retry_after: float, **kwargs: Any):
        self.retry_after = retry_after
        super().__init__(
            status=429,
            code="RATE_LIMITED",
            message=f"Rate limited, retry after {retry_after}s",
        )


# =============================================================================
# Gateway Errors
# =============================================================================


class GatewayException(FluxerException):
    """Base for gateway/WebSocket errors."""


class GatewayNotConnected(GatewayException):
    """Raised when trying to use the gateway before it's connected."""


class ReconnectRequested(GatewayException):
    """The gateway has requested we reconnect."""


class SessionInvalid(GatewayException):
    """The session is invalid and cannot be resumed."""

    def __init__(self, resumable: bool = False):
        self.resumable = resumable
        super().__init__(f"Invalid session (resumable={resumable})")


# =============================================================================
# Client Errors
# =============================================================================


class LoginFailure(FluxerException):
    """Raised when the bot token is invalid."""


# Map HTTP status codes to exception classes
_STATUS_MAP: dict[int, type[HTTPException]] = {
    400: BadRequest,
    401: Unauthorized,
    403: Forbidden,
    404: NotFound,
    429: RateLimited,
}


def http_exception_from_status(
    status: int, code: str, message: str, **kwargs: Any
) -> HTTPException:
    """Factory to create the right HTTPException subclass for a status code."""
    cls = _STATUS_MAP.get(status, HTTPException)
    if cls is RateLimited:
        return RateLimited(retry_after=kwargs.get("retry_after", 0.0))
    return cls(status=status, code=code, message=message, errors=kwargs.get("errors"))
