"""Public request/response schemas for Stage 5 vision inference."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings

VisionMediaType = Literal["image/png", "image/jpeg", "image/webp"]


class VisionImageInput(BaseModel):
    """One base64-encoded image accepted by the local vision endpoint."""

    media_type: VisionMediaType
    data_base64: str = Field(
        min_length=1,
        max_length=((settings.vision_max_image_bytes + 2) // 3) * 4 + 32,
    )


class VisionRequest(BaseModel):
    """One bounded, free-form multimodal request."""

    prompt: str = Field(min_length=1, max_length=50_000)
    images: list[VisionImageInput] = Field(
        min_length=1,
        max_length=settings.vision_max_images,
    )
    system: str | None = Field(default=None, max_length=20_000)
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=2048, ge=1, le=8192)


class VisionImageInfo(BaseModel):
    """Content-free preprocessing metadata for one accepted image."""

    media_type: VisionMediaType
    original_width: int
    original_height: int
    width: int
    height: int
    input_bytes: int
    processed_bytes: int


class VisionResponse(BaseModel):
    """Free-form vision result plus operational metadata."""

    text: str
    model: str
    profile: Literal["vision"] = "vision"
    image_count: int
    images: list[VisionImageInfo]
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    tokens_per_second: float | None = None
    time_to_first_token_seconds: float | None = None
    model_load_time_seconds: float | None = None
    request_id: str


class VisionStatusResponse(BaseModel):
    """Configured vision-model discovery state reported without loading the model."""

    model: str
    installed: bool
    supports_vision: bool
    loaded: bool
