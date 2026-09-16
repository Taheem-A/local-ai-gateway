"""FastAPI router for caller-owned tool calling plus mounted extension routes."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, Header

from app.config import settings
from app.errors import AuthenticationError, GatewayError, LMStudioUnavailableError
from app.lmstudio import LMStudioError
from app.observability import RequestMetric, record_metric
from app.playground.router import router as playground_router
from app.routing import choose_profile
from app.schemas import ToolTurnRequest, ToolTurnResponse
from app.streaming.router import router as streaming_router
from app.tools.service import run_tool_turn
from app.vision.router import router as vision_router

router = APIRouter()
# `app.main` already mounts this router as the gateway's extension router. Keep
# extension features in their own modules while composing them here to avoid
# duplicating application setup and exception handling.
router.include_router(streaming_router)
router.include_router(vision_router)
router.include_router(playground_router)


def _authenticate(key: str | None) -> None:
    """Apply the same local API-key boundary as the gateway's core routes."""

    if key != settings.gateway_api_key:
        raise AuthenticationError()


def _record_failure(
    *,
    request_id: str,
    project: str | None,
    request: ToolTurnRequest,
    started: float,
    error_code: str,
) -> None:
    """Record tool-planning failures without persisting messages, tools, or arguments."""

    profile = choose_profile(request.quality, request.reasoning)
    record_metric(
        RequestMetric(
            request_id=request_id,
            project=project,
            endpoint="/v1/tools/turn",
            quality=profile.name,
            model=profile.model,
            reasoning_level=profile.reasoning,
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


@router.post("/v1/tools/turn", response_model=ToolTurnResponse)
async def tool_turn_endpoint(
    request: ToolTurnRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> ToolTurnResponse:
    """Run one model turn and return validated tool requests without executing them."""

    _authenticate(x_local_ai_key)
    request_id = str(uuid4())
    profile = choose_profile(request.quality, request.reasoning)
    started = time.perf_counter()

    try:
        result = await run_tool_turn(
            request=request,
            model=profile.model,
            reasoning=profile.reasoning,
        )
    except GatewayError as exc:
        _record_failure(
            request_id=request_id,
            project=x_project_id,
            request=request,
            started=started,
            error_code=exc.code,
        )
        raise
    except LMStudioError as exc:
        _record_failure(
            request_id=request_id,
            project=x_project_id,
            request=request,
            started=started,
            error_code="LMSTUDIO_UNAVAILABLE",
        )
        raise LMStudioUnavailableError(str(exc)) from exc

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/tools/turn",
            quality=profile.name,
            model=result.model,
            reasoning_level=profile.reasoning,
            input_tokens=result.input_tokens,
            reasoning_tokens=result.reasoning_output_tokens,
            output_tokens=result.output_tokens,
            model_load_seconds=None,
            first_token_seconds=None,
            total_latency_seconds=time.perf_counter() - started,
            attempts=1,
            success=True,
        )
    )

    return ToolTurnResponse(
        status=result.status,
        text=result.text,
        tool_calls=result.tool_calls,
        assistant_message=result.assistant_message,
        model=result.model,
        profile=profile.name,
        reasoning=profile.reasoning,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        reasoning_output_tokens=result.reasoning_output_tokens,
        finish_reason=result.finish_reason,
        request_id=request_id,
    )
