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
from app.rag import (
    answer_with_rag,
    delete_collection as rag_delete_collection,
    delete_document as rag_delete_document,
    embed_public_inputs,
    index_documents,
    initialize_rag_db,
    list_collections as rag_list_collections,
    search_collection,
)
from app.routing import ModelProfile, choose_profile, public_profiles
from app.schemas import (
    ClassifyRequest,
    ClassifyResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ExtractRequest,
    ExtractResponse,
    GenerateRequest,
    GenerateResponse,
    RagAnswerRequest,
    RagAnswerResponse,
    RagCollectionsResponse,
    RagDeleteResponse,
    RagIndexRequest,
    RagIndexResponse,
    RagSearchRequest,
    RagSearchResponse,
    StatusResponse,
)
from app.structured import run_structured


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize local persistence once when the API process starts."""

    initialize_metrics_db()
    initialize_rag_db()
    yield


app = FastAPI(
    title="Local AI Gateway",
    version="3.0.0",
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
    """Record a failed generation-profile request without storing content."""

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


def _record_aux_failure_metric(
    *,
    request_id: str,
    project: str | None,
    endpoint: str,
    quality: str,
    model: str | None,
    started: float,
    error_code: str,
) -> None:
    """Record failed embedding/RAG work that does not use a generation profile."""

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=project,
            endpoint=endpoint,
            quality=quality,
            model=model,
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
) -> dict[str, Any]:
    """Expose public generation profiles and the configured embedding model."""

    authenticate(x_local_ai_key)
    return {
        "profiles": public_profiles(),
        "embedding": {"model": settings.embedding_model},
    }


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
            embedding_model=settings.embedding_model,
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
        embedding_model=settings.embedding_model,
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


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def embeddings_endpoint(
    request: EmbeddingRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> EmbeddingResponse:
    """Generate reusable dense vectors using the configured embedding model."""

    authenticate(x_local_ai_key)
    request_id = _request_id()
    started = time.perf_counter()
    texts = [request.input] if isinstance(request.input, str) else request.input

    try:
        result = await embed_public_inputs(texts, purpose=request.purpose)
    except LMStudioError as exc:
        _record_aux_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/embeddings",
            quality="embedding",
            model=settings.embedding_model,
            started=started,
            error_code="LMSTUDIO_UNAVAILABLE",
        )
        raise LMStudioUnavailableError(str(exc)) from exc

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/embeddings",
            quality="embedding",
            model=result.model,
            reasoning_level=None,
            input_tokens=result.input_tokens,
            reasoning_tokens=None,
            output_tokens=0,
            model_load_seconds=None,
            first_token_seconds=None,
            total_latency_seconds=time.perf_counter() - started,
            attempts=1,
            success=True,
        )
    )
    return EmbeddingResponse(
        embeddings=result.vectors,
        model=result.model,
        dimensions=result.dimensions,
        input_tokens=result.input_tokens,
        request_id=request_id,
    )


@app.post("/v1/rag/index", response_model=RagIndexResponse)
async def rag_index_endpoint(
    request: RagIndexRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> RagIndexResponse:
    """Chunk and index documents, replacing matching document IDs atomically."""

    authenticate(x_local_ai_key)
    request_id = _request_id()
    started = time.perf_counter()
    chunk_size = request.chunk_size_chars or settings.rag_chunk_size_chars
    chunk_overlap = (
        request.chunk_overlap_chars
        if request.chunk_overlap_chars is not None
        else settings.rag_chunk_overlap_chars
    )

    try:
        result = await index_documents(
            collection=request.collection,
            documents=[document.model_dump() for document in request.documents],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except GatewayError as exc:
        _record_aux_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/rag/index",
            quality="rag-index",
            model=settings.embedding_model,
            started=started,
            error_code=exc.code,
        )
        raise
    except LMStudioError as exc:
        _record_aux_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/rag/index",
            quality="rag-index",
            model=settings.embedding_model,
            started=started,
            error_code="LMSTUDIO_UNAVAILABLE",
        )
        raise LMStudioUnavailableError(str(exc)) from exc

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/rag/index",
            quality="rag-index",
            model=result["embedding_model"],
            reasoning_level=None,
            input_tokens=result["embedding_input_tokens"],
            reasoning_tokens=None,
            output_tokens=0,
            model_load_seconds=None,
            first_token_seconds=None,
            total_latency_seconds=time.perf_counter() - started,
            attempts=1,
            success=True,
        )
    )
    return RagIndexResponse(
        collection=result["collection"],
        documents=result["documents"],
        chunks=result["chunks"],
        embedding_model=result["embedding_model"],
        embedding_dimensions=result["embedding_dimensions"],
        request_id=request_id,
    )


@app.post("/v1/rag/search", response_model=RagSearchResponse)
async def rag_search_endpoint(
    request: RagSearchRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> RagSearchResponse:
    """Return semantically similar chunks without invoking a generation model."""

    authenticate(x_local_ai_key)
    request_id = _request_id()
    started = time.perf_counter()

    try:
        hits, embedding = await search_collection(
            collection=request.collection,
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            metadata_filter=request.metadata_filter,
        )
    except GatewayError as exc:
        _record_aux_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/rag/search",
            quality="rag-search",
            model=settings.embedding_model,
            started=started,
            error_code=exc.code,
        )
        raise
    except LMStudioError as exc:
        _record_aux_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/rag/search",
            quality="rag-search",
            model=settings.embedding_model,
            started=started,
            error_code="LMSTUDIO_UNAVAILABLE",
        )
        raise LMStudioUnavailableError(str(exc)) from exc

    record_metric(
        RequestMetric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/rag/search",
            quality="rag-search",
            model=embedding.model,
            reasoning_level=None,
            input_tokens=embedding.input_tokens,
            reasoning_tokens=None,
            output_tokens=0,
            model_load_seconds=None,
            first_token_seconds=None,
            total_latency_seconds=time.perf_counter() - started,
            attempts=1,
            success=True,
        )
    )
    return RagSearchResponse(
        collection=request.collection,
        hits=hits,
        embedding_model=embedding.model,
        request_id=request_id,
    )


@app.post("/v1/rag/answer", response_model=RagAnswerResponse)
async def rag_answer_endpoint(
    request: RagAnswerRequest,
    x_local_ai_key: str | None = Header(default=None),
    x_project_id: str | None = Header(default=None),
) -> RagAnswerResponse:
    """Retrieve local evidence and generate a citation-constrained grounded answer."""

    authenticate(x_local_ai_key)
    request_id = _request_id()
    profile = choose_profile(request.quality, request.reasoning)
    started = time.perf_counter()

    try:
        result = await answer_with_rag(
            collection=request.collection,
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            metadata_filter=request.metadata_filter,
            generation_model=profile.model,
            reasoning=profile.reasoning,
            system=request.system,
            max_output_tokens=request.max_output_tokens,
        )
    except GatewayError as exc:
        _record_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/rag/answer",
            profile=profile,
            started=started,
            attempts=settings.structured_max_attempts,
            error_code=exc.code,
        )
        raise
    except LMStudioError as exc:
        _record_failure_metric(
            request_id=request_id,
            project=x_project_id,
            endpoint="/v1/rag/answer",
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
            endpoint="/v1/rag/answer",
            quality=profile.name,
            model=result.model or settings.embedding_model,
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
    return RagAnswerResponse(
        answer=result.answer,
        citations=result.citations,
        retrieved=result.retrieved,
        model=result.model,
        profile=profile.name,
        reasoning=profile.reasoning,
        attempts=result.attempts,
        request_id=request_id,
    )


@app.get("/v1/rag/collections", response_model=RagCollectionsResponse)
async def rag_collections_endpoint(
    x_local_ai_key: str | None = Header(default=None),
) -> RagCollectionsResponse:
    """List all persistent RAG collections and their embedding signatures."""

    authenticate(x_local_ai_key)
    return RagCollectionsResponse(collections=rag_list_collections())


@app.delete("/v1/rag/collections/{collection}", response_model=RagDeleteResponse)
async def rag_delete_collection_endpoint(
    collection: str,
    x_local_ai_key: str | None = Header(default=None),
) -> RagDeleteResponse:
    """Delete an entire RAG collection."""

    authenticate(x_local_ai_key)
    return RagDeleteResponse(deleted_chunks=rag_delete_collection(collection))


@app.delete(
    "/v1/rag/collections/{collection}/documents/{document_id}",
    response_model=RagDeleteResponse,
)
async def rag_delete_document_endpoint(
    collection: str,
    document_id: str,
    x_local_ai_key: str | None = Header(default=None),
) -> RagDeleteResponse:
    """Delete one indexed document without affecting the rest of the collection."""

    authenticate(x_local_ai_key)
    return RagDeleteResponse(
        deleted_chunks=rag_delete_document(collection, document_id)
    )
