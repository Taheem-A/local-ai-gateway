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


class VisionProviderUnavailableError(GatewayError):
    """Raised when LM Studio cannot currently accept a vision request."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="VISION_PROVIDER_UNAVAILABLE",
            message=message,
            status_code=503,
            details=details,
        )


class VisionProviderTimeoutError(GatewayError):
    """Raised when the local multimodal provider exceeds the gateway timeout."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="VISION_PROVIDER_TIMEOUT",
            message=message,
            status_code=504,
            details=details,
        )


class VisionProviderRejectedError(GatewayError):
    """Raised when LM Studio rejects a gateway-generated multimodal request."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="VISION_PROVIDER_REJECTED",
            message=message,
            status_code=502,
            details=details,
        )


class VisionRuntimeError(GatewayError):
    """Raised when the model/backend terminates or crashes during image inference."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="VISION_RUNTIME_FAILED",
            message=message,
            status_code=502,
            details=details,
        )


class VisionProtocolError(GatewayError):
    """Raised when LM Studio returns a malformed or unexpected response shape."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="VISION_PROVIDER_PROTOCOL",
            message=message,
            status_code=502,
            details=details,
        )


class VisionOutputError(GatewayError):
    """Raised when a successful provider turn contains no user-visible answer."""

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            code="VISION_OUTPUT_EMPTY",
            message=message,
            status_code=502,
            details=details,
        )
