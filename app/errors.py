from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GatewayError(Exception):
    code: str
    message: str
    status_code: int = 500
    details: Any | None = None

    def __str__(self) -> str:
        return self.message


class AuthenticationError(GatewayError):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_FAILED",
            message="Invalid API key.",
            status_code=401,
        )


class LMStudioUnavailableError(GatewayError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="LMSTUDIO_UNAVAILABLE",
            message=message,
            status_code=502,
            details=details,
        )


class StructuredOutputError(GatewayError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="OUTPUT_INVALID",
            message=message,
            status_code=422,
            details=details,
        )
