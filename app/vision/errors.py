"""Stable Stage 5 vision errors surfaced through the gateway envelope."""

from __future__ import annotations

from typing import Any

from app.errors import GatewayError


class VisionInputError(GatewayError):
    """Raised when an image is invalid, unsupported, or outside configured bounds."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="VISION_INPUT_INVALID",
            message=message,
            status_code=422,
            details=details,
        )


class VisionModelError(GatewayError):
    """Raised when the configured local model cannot serve vision requests."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="VISION_MODEL_UNAVAILABLE",
            message=message,
            status_code=503,
            details=details,
        )
