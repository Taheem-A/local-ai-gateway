"""Client-side exceptions for stable gateway error responses."""

from __future__ import annotations

from typing import Any


class AIError(RuntimeError):
    """Expose the gateway error code and structured details to Python callers."""

    def __init__(self, code: str, message: str, details: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
