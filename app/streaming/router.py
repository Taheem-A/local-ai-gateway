"""FastAPI endpoint for provider-independent incremental text generation."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.errors import AuthenticationError
from app.lmstudio import LMStudioError
from app.observability import RequestMetric, record_metric
from app.routing import ModelProfile, choose_profile
from app.schemas import GenerateRequest
from app.streaming.provider import stream_generate
from app.streaming.sse import encode_sse

router = APIRouter()


def _authenticate(key: str | None) -> None:
    """Apply the gateway's local API-key boundary before streaming begins."""

    if key != settings.gateway_api_key:
        raise AuthenticationError()


def _record_failure(
    *,
    request_id: str,
    project: str | None,
    profile: ModelProfile,
    started: float,
    error_code: str,
) -> None:
    """Record one failed/cancelled stream without persisting any generated text."""

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=project,
            endpoint="/v1/generate/stream",
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


def _public_error(request_id: str, code: str, message: str) -> str:
    """Return an in-band error event for failures after SSE headers are committed."""

    return encode_sse(
        "error",
        {
            "request_id": request_id,
            "error": {
                "code": code,
                "message": message,
                "details": None,
            },
        },
    )


@router.post("/v1/generate/stream")
async def generate_stream_endpoint(
    payload: GenerateRequest,
    http_request: Request,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> StreamingResponse:
    """Stream user-visible text deltas while retaining a stable gateway SSE contract."""

    _authenticate(x_local_ai_key)
    request_id = str(uuid4())
    profile = choose_profile(payload.quality, payload.reasoning)
    started = time.perf_counter()

    async def events() -> AsyncIterator[str]:
        provider = stream_generate(
            model=profile.model,
            prompt=payload.prompt,
            system=payload.system,
            reasoning=profile.reasoning,
            temperature=payload.temperature,
            max_output_tokens=payload.max_output_tokens,
        )
        metric_recorded = False
        first_text_seconds: float | None = None

        yield encode_sse(
            "start",
            {
                "request_id": request_id,
                "model": profile.model,
                "profile": profile.name,
                "quality": payload.quality,
                "reasoning": profile.reasoning,
            },
        )

        try:
            async for event in provider:
                if await http_request.is_disconnected():
                    _record_failure(
                        request_id=request_id,
                        project=x_project_id,
                        profile=profile,
                        started=started,
                        error_code="CLIENT_DISCONNECTED",
                    )
                    metric_recorded = True
                    return

                event_type = event["type"]
                if event_type == "progress":
                    public_event = dict(event)
                    public_event["request_id"] = request_id
                    yield encode_sse("progress", public_event)
                    continue

                if event_type == "delta":
                    if first_text_seconds is None:
                        first_text_seconds = time.perf_counter() - started
                    yield encode_sse(
                        "delta",
                        {
                            "request_id": request_id,
                            "text": event["text"],
                        },
                    )
                    continue

                if event_type != "completed":
                    continue

                total_latency = time.perf_counter() - started
                provider_first_token = event.get("time_to_first_token_seconds")
                record_metric(
                    RequestMetric(
                        request_id=request_id,
                        project=x_project_id,
                        endpoint="/v1/generate/stream",
                        quality=profile.name,
                        model=event["model"],
                        reasoning_level=profile.reasoning,
                        input_tokens=event.get("input_tokens"),
                        reasoning_tokens=event.get("reasoning_output_tokens"),
                        output_tokens=event.get("output_tokens"),
                        model_load_seconds=event.get("model_load_time_seconds"),
                        first_token_seconds=provider_first_token,
                        total_latency_seconds=total_latency,
                        attempts=1,
                        success=True,
                    )
                )
                metric_recorded = True

                completed: dict[str, Any] = dict(event)
                completed.update(
                    {
                        "request_id": request_id,
                        "profile": profile.name,
                        "quality": payload.quality,
                        "reasoning": profile.reasoning,
                        "time_to_first_text_seconds": first_text_seconds,
                        "total_latency_seconds": total_latency,
                    }
                )
                yield encode_sse("completed", completed)
                return
        except asyncio.CancelledError:
            if not metric_recorded:
                _record_failure(
                    request_id=request_id,
                    project=x_project_id,
                    profile=profile,
                    started=started,
                    error_code="CLIENT_DISCONNECTED",
                )
                metric_recorded = True
            raise
        except LMStudioError:
            if not metric_recorded:
                _record_failure(
                    request_id=request_id,
                    project=x_project_id,
                    profile=profile,
                    started=started,
                    error_code="LMSTUDIO_UNAVAILABLE",
                )
                metric_recorded = True
            yield _public_error(
                request_id,
                "LMSTUDIO_UNAVAILABLE",
                "LM Studio was unavailable or the provider stream failed.",
            )
        except Exception:
            if not metric_recorded:
                _record_failure(
                    request_id=request_id,
                    project=x_project_id,
                    profile=profile,
                    started=started,
                    error_code="STREAM_FAILED",
                )
                metric_recorded = True
            yield _public_error(
                request_id,
                "STREAM_FAILED",
                "The generation stream failed unexpectedly.",
            )
        finally:
            await provider.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )
