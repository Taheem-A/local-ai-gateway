"""Stable gateway exception types used by HTTP handlers and SDK clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GatewayError(Exception):
    """Base exception carrying an API-safe code, status, and optional details."""

    code: str
    message: str
    status_code: int = 500
    details: Any | None = None

    def __str__(self) -> str:
        return self.message


class AuthenticationError(GatewayError):
    """Raised when a request does not present the configured gateway key."""

    def __init__(self) -> None:
        super().__init__(
            code="AUTH_FAILED",
            message="Invalid API key.",
            status_code=401,
        )


class LMStudioUnavailableError(GatewayError):
    """Translate an LM Studio transport/provider failure into a stable 502 error."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="LMSTUDIO_UNAVAILABLE",
            message=message,
            status_code=502,
            details=details,
        )


class StructuredOutputError(GatewayError):
    """Raised after bounded structured-output attempts still fail validation."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="OUTPUT_INVALID",
            message=message,
            status_code=422,
            details=details,
        )
