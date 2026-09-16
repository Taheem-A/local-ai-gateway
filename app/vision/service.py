"""Stage 5 vision orchestration and model-capability checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anyio import to_thread

from app.config import settings
from app.lmstudio import list_models
from app.vision.errors import VisionModelError
from app.vision.images import PreparedVisionImage, prepare_vision_images
from app.vision.provider import generate_vision
from app.vision.schemas import VisionImageInfo, VisionRequest


@dataclass(frozen=True)
class VisionModelStatus:
    model: str
    installed: bool
    supports_vision: bool
    loaded: bool


@dataclass(frozen=True)
class VisionResult:
    text: str
    model: str
    images: list[VisionImageInfo]
    input_tokens: int | None
    output_tokens: int | None
    reasoning_output_tokens: int | None
    tokens_per_second: float | None
    time_to_first_token_seconds: float | None
    model_load_time_seconds: float | None


def _model_identifier(model: dict[str, Any]) -> str | None:
    value = model.get("key") or model.get("id") or model.get("model")
    return str(value) if value else None


def _is_loaded(model: dict[str, Any]) -> bool:
    instances = model.get("loaded_instances")
    if isinstance(instances, list) and instances:
        return True
    # Retain compatibility with older LM Studio inventory shapes.
    state = str(model.get("state") or "").lower()
    return state in {"loaded", "ready", "idle", "generating"}


def inspect_vision_model(models: list[dict[str, Any]]) -> VisionModelStatus:
    """Resolve the configured model against LM Studio's capability inventory."""

    for model in models:
        if _model_identifier(model) != settings.vision_model:
            continue
        capabilities = model.get("capabilities") or {}
        supports_vision = bool(
            isinstance(capabilities, dict) and capabilities.get("vision") is True
        )
        return VisionModelStatus(
            model=settings.vision_model,
            installed=True,
            supports_vision=supports_vision,
            loaded=_is_loaded(model),
        )
    return VisionModelStatus(
        model=settings.vision_model,
        installed=False,
        supports_vision=False,
        loaded=False,
    )


async def vision_model_status() -> VisionModelStatus:
    """Read vision availability without loading or invoking the configured model."""

    return inspect_vision_model(await list_models())


async def run_vision(request: VisionRequest) -> VisionResult:
    """Validate images, verify model capability, and perform one local VLM turn."""

    prepared: list[PreparedVisionImage] = await to_thread.run_sync(
        prepare_vision_images,
        request.images,
    )
    status = await vision_model_status()
    if not status.installed:
        raise VisionModelError(
            "The configured vision model is not installed in LM Studio.",
            details={"model": settings.vision_model},
        )
    if not status.supports_vision:
        raise VisionModelError(
            "The configured LM Studio model does not advertise vision input support.",
            details={"model": settings.vision_model},
        )

    result = await generate_vision(
        prompt=request.prompt,
        images=prepared,
        system=request.system,
        temperature=request.temperature,
        max_output_tokens=request.max_output_tokens,
    )
    image_info = [
        VisionImageInfo(
            media_type=image.media_type,
            original_width=image.original_width,
            original_height=image.original_height,
            width=image.width,
            height=image.height,
            input_bytes=image.input_bytes,
            processed_bytes=image.processed_bytes,
        )
        for image in prepared
    ]
    return VisionResult(
        text=result["text"],
        model=result["model"],
        images=image_info,
        input_tokens=result.get("input_tokens"),
        output_tokens=result.get("output_tokens"),
        reasoning_output_tokens=result.get("reasoning_output_tokens"),
        tokens_per_second=result.get("tokens_per_second"),
        time_to_first_token_seconds=result.get("time_to_first_token_seconds"),
        model_load_time_seconds=result.get("model_load_time_seconds"),
    )
