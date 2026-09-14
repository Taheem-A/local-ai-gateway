"""FastAPI entry point for the localhost-only Local AI Gateway."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.errors import AuthenticationError, GatewayError, LMStudioUnavailableError
from app.lmstudio import LMStudioError, generate, list_models
from app.observability import RequestMetric, initialize_metrics_db, record_metric
from app.routing import ModelProfile, choose_profile, public_profiles
from app.schemas import (
    ClassifyRequest,
    ClassifyResponse,
    ExtractRequest,
    ExtractResponse,
    GenerateRequest,
    GenerateResponse,
    StatusResponse,
)
from app.structured import run_structured


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize local persistence once when the API process starts."""

    initialize_metrics_db()
    yield


app = FastAPI(
    title="Local AI Gateway",
    version="2.0.0",
    lifespan=lifespan,
)


def authenticate(x_local_ai_key: str | None) -> None:
    """Reject requests that do not provide the configured local gateway key."""

    if x_local_ai_key != settings.gateway_api_key:
        raise AuthenticationError()


def _request_id() -> str:
    """Return an opaque identifier for metrics and client-side troubleshooting."""

    return str(uuid4())


def _record_failure_metric(
    *,
    request_id: str,
    project: str | None,
    endpoint: str,
    profile: ModelProfile,
    started: float,
    attempts: int,
    error_code: str,
) -> None:
    """Record a failed gateway request without persisting prompt or response content."""

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=project,
            endpoint=endpoint,
            quality=profile.name,
            model=profile.model,
            reasoning_level=profile.reasoning,
            input_tokens=None,
            reasoning_tokens=None,
            output_tokens=None,
            model_load_seconds=None,
            first_token_seconds=None,
            total_latency_seconds=time.perf_counter() - started,
            attempts=attempts,
            success=False,
            error_code=error_code,
        )
    )


@app.exception_handler(GatewayError)
async def gateway_error_handler(_: Request, exc: GatewayError) -> JSONResponse:
    """Render gateway-owned exceptions using one stable JSON error envelope."""

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Translate Pydantic/FastAPI validation failures into the gateway error shape."""

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": "The request did not match the API schema.",
                "details": exc.errors(),
            }
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Return process health without invoking LM Studio or loading a model."""

    return {"status": "ok"}


@app.get("/v1/models")
async def models_endpoint(
    x_local_ai_key: str | None = Header(default=None),
) -> dict[str, dict[str, dict[str, str | None]]]:
    """Expose public profile mappings rather than requiring callers to know model IDs."""

    authenticate(x_local_ai_key)
    return {"profiles": public_profiles()}


@app.get("/v1/status", response_model=StatusResponse)
async def status_endpoint(
    x_local_ai_key: str | None = Header(default=None),
) -> StatusResponse:
    """Return gateway configuration plus LM Studio availability and loaded models."""

    authenticate(x_local_ai_key)
    try:
        models = await list_models()
    except LMStudioError:
        return StatusResponse(
            lmstudio="unavailable",
            loaded_models=[],
            profiles=public_profiles(),
        )

    loaded: list[str] = []
    for model in models:
        state = str(model.get("state", "")).lower()
        if state in {"loaded", "ready", "idle", "generating"}:
            identifier = model.get("id") or model.get("key") or model.get("model")
            if identifier:
                loaded.append(str(identifier))

    return StatusResponse(
        lmstudio="ok",
        loaded_models=loaded,
        profiles=public_profiles(),
    )


@app.post("/v1/generate", response_model=GenerateResponse)
async def generate_endpoint(
    request: GenerateRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> GenerateResponse:
    """Generate free-form text using a profile-selected local model."""

    authenticate(x_local_ai_key)
    request_id = _request_id()
    profile = choose_profile(request.quality, request.reasoning)
    started = time.perf_counter()

    try:
        result = await generate(
            model=profile.model,
            prompt=request.prompt,
            system=request.system,
            reasoning=profile.reasoning,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
        )
    except LMStudioError as exc:
        _record_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/generate",
            profile=profile,
            started=started,
            attempts=1,
            error_code="LMSTUDIO_UNAVAILABLE",
        )
        raise LMStudioUnavailableError(str(exc)) from exc

    latency = time.perf_counter() - started
    record_metric(
        RequestMetric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/generate",
            quality=profile.name,
            model=result["model"],
            reasoning_level=profile.reasoning,
            input_tokens=result["input_tokens"],
            reasoning_tokens=result.get("reasoning_output_tokens"),
            output_tokens=result["output_tokens"],
            model_load_seconds=result["model_load_time_seconds"],
            first_token_seconds=result["time_to_first_token_seconds"],
            total_latency_seconds=latency,
            attempts=1,
            success=True,
        )
    )

    return GenerateResponse(
        text=result["text"],
        model=result["model"],
        profile=profile.name,
        quality=request.quality,
        reasoning=profile.reasoning,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        reasoning_output_tokens=result.get("reasoning_output_tokens"),
        tokens_per_second=result["tokens_per_second"],
        time_to_first_token_seconds=result["time_to_first_token_seconds"],
        model_load_time_seconds=result["model_load_time_seconds"],
        request_id=request_id,
    )


@app.post("/v1/extract", response_model=ExtractResponse)
async def extract_endpoint(
    request: ExtractRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> ExtractResponse:
    """Return locally validated data constrained by a caller-supplied JSON Schema."""

    authenticate(x_local_ai_key)
    request_id = _request_id()
    profile = choose_profile(request.quality, request.reasoning)
    started = time.perf_counter()

    try:
        result = await run_structured(
            model=profile.model,
            prompt=request.prompt,
            schema=request.schema_,
            system=request.system,
            reasoning=profile.reasoning,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            max_attempts=request.max_attempts,
        )
    except GatewayError as exc:
        _record_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/extract",
            profile=profile,
            started=started,
            attempts=request.max_attempts,
            error_code=exc.code,
        )
        raise
    except LMStudioError as exc:
        _record_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/extract",
            profile=profile,
            started=started,
            attempts=1,
            error_code="LMSTUDIO_UNAVAILABLE",
        )
        raise LMStudioUnavailableError(str(exc)) from exc

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/extract",
            quality=profile.name,
            model=result.model,
            reasoning_level=profile.reasoning,
            input_tokens=result.input_tokens,
            reasoning_tokens=result.reasoning_output_tokens,
            output_tokens=result.output_tokens,
            model_load_seconds=None,
            first_token_seconds=None,
            total_latency_seconds=time.perf_counter() - started,
            attempts=result.attempts,
            success=True,
        )
    )

    return ExtractResponse(
        data=result.data,
        model=result.model,
        profile=profile.name,
        reasoning=profile.reasoning,
        attempts=result.attempts,
        request_id=request_id,
    )


@app.post("/v1/classify", response_model=ClassifyResponse)
async def classify_endpoint(
    request: ClassifyRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> ClassifyResponse:
    """Classify text into exactly one caller-provided label using constrained JSON."""

    authenticate(x_local_ai_key)
    request_id = _request_id()
    profile = choose_profile(request.quality, request.reasoning)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"label": {"type": "string", "enum": request.labels}},
        "required": ["label"],
        "additionalProperties": False,
    }
    allowed_labels = ", ".join(request.labels)
    prompt = (
        "Classify the following text into exactly one allowed label. "
        "Use the label spelling exactly as provided. Return only the schema-constrained result.\n\n"
        f"Allowed labels: {allowed_labels}\n\n"
        f"Text:\n{request.text}"
    )
    started = time.perf_counter()

    try:
        result = await run_structured(
            model=profile.model,
            prompt=prompt,
            schema=schema,
            system=request.system,
            reasoning=profile.reasoning,
            temperature=0.0,
            max_output_tokens=request.max_output_tokens,
            max_attempts=request.max_attempts,
        )
    except GatewayError as exc:
        _record_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/classify",
            profile=profile,
            started=started,
            attempts=request.max_attempts,
            error_code=exc.code,
        )
        raise
    except LMStudioError as exc:
        _record_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/classify",
            profile=profile,
            started=started,
            attempts=1,
            error_code="LMSTUDIO_UNAVAILABLE",
        )
        raise LMStudioUnavailableError(str(exc)) from exc

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/classify",
            quality=profile.name,
            model=result.model,
            reasoning_level=profile.reasoning,
            input_tokens=result.input_tokens,
            reasoning_tokens=result.reasoning_output_tokens,
            output_tokens=result.output_tokens,
            model_load_seconds=None,
            first_token_seconds=None,
            total_latency_seconds=time.perf_counter() - started,
            attempts=result.attempts,
            success=True,
        )
    )

    return ClassifyResponse(
        label=result.data["label"],
        model=result.model,
        profile=profile.name,
        reasoning=profile.reasoning,
        attempts=result.attempts,
        request_id=request_id,
    )
