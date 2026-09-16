"""Authenticated Stage 5 vision endpoint and local capability status."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, Header

from app.config import settings
from app.errors import AuthenticationError, GatewayError, LMStudioUnavailableError
from app.lmstudio import LMStudioError
from app.observability import RequestMetric, record_metric
from app.vision.schemas import VisionRequest, VisionResponse, VisionStatusResponse
from app.vision.service import run_vision, vision_model_status

router = APIRouter()


def _authenticate(key: str | None) -> None:
    if key != settings.gateway_api_key:
        raise AuthenticationError()


def _record_failure(
    *,
    request_id: str,
    project: str | None,
    started: float,
    error_code: str,
) -> None:
    record_metric(
        RequestMetric(
            request_id=request_id,
            project=project,
            endpoint="/v1/vision",
            quality="vision",
            model=settings.vision_model,
            reasoning_level=None,
            input_tokens=None,
            reasoning_tokens=None,
            output_tokens=None,
            model_load_seconds=None,
            first_token_seconds=None,
            total_latency_seconds=time.perf_counter() - started,
            attempts=1,
            success=False,
            error_code=error_code,
        )
    )


@router.get("/v1/vision/status", response_model=VisionStatusResponse)
async def vision_status_endpoint(
    x_local_ai_key: str | None = Header(default=None),
) -> VisionStatusResponse:
    """Report configured VLM installation/capability state without loading it."""

    _authenticate(x_local_ai_key)
    try:
        status = await vision_model_status()
    except LMStudioError as exc:
        raise LMStudioUnavailableError(str(exc)) from exc
    return VisionStatusResponse(
        model=status.model,
        installed=status.installed,
        supports_vision=status.supports_vision,
        loaded=status.loaded,
    )


@router.post("/v1/vision", response_model=VisionResponse)
async def vision_endpoint(
    payload: VisionRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> VisionResponse:
    """Analyze one bounded local image batch without persisting image or prompt content."""

    _authenticate(x_local_ai_key)
    request_id = str(uuid4())
    started = time.perf_counter()

    try:
        result = await run_vision(payload)
    except GatewayError as exc:
        _record_failure(
            request_id=request_id,
            project=x_project_id,
            started=started,
            error_code=exc.code,
        )
        raise
    except LMStudioError as exc:
        _record_failure(
            request_id=request_id,
            project=x_project_id,
            started=started,
            error_code="LMSTUDIO_UNAVAILABLE",
        )
        raise LMStudioUnavailableError(str(exc)) from exc

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/vision",
            quality="vision",
            model=result.model,
            reasoning_level=None,
            input_tokens=result.input_tokens,
            reasoning_tokens=result.reasoning_output_tokens,
            output_tokens=result.output_tokens,
            model_load_seconds=result.model_load_time_seconds,
            first_token_seconds=result.time_to_first_token_seconds,
            total_latency_seconds=time.perf_counter() - started,
            attempts=1,
            success=True,
        )
    )

    return VisionResponse(
        text=result.text,
        model=result.model,
        image_count=len(result.images),
        images=result.images,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        reasoning_output_tokens=result.reasoning_output_tokens,
        tokens_per_second=result.tokens_per_second,
        time_to_first_token_seconds=result.time_to_first_token_seconds,
        model_load_time_seconds=result.model_load_time_seconds,
        request_id=request_id,
    )
