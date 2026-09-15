"""LM Studio provider adapters for generation, tools, embeddings, and model discovery."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class LMStudioError(RuntimeError):
    """Raised when LM Studio returns an unusable or unsuccessful response."""


def _headers() -> dict[str, str]:
    """Return the shared authorization headers for local LM Studio requests."""

    return {
        "Authorization": f"Bearer {settings.lm_api_token}",
        "Content-Type": "application/json",
    }


def _timeout() -> httpx.Timeout:
    """Return the provider timeout configured for local inference."""

    return httpx.Timeout(settings.lm_timeout_seconds)


async def generate(
    *,
    model: str,
    prompt: str,
    system: str | None,
    reasoning: str | None,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Generate free-form text through LM Studio's native chat endpoint."""

    body: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "context_length": settings.default_context_length,
        "store": False,
    }
    if system:
        body["system_prompt"] = system
    if reasoning:
        body["reasoning"] = reasoning

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        response = await client.post(
            f"{settings.lm_base_url}/api/v1/chat",
            headers=_headers(),
            json=body,
        )

    if not response.is_success:
        raise LMStudioError(f"LM Studio returned {response.status_code}: {response.text}")

    data = response.json()
    # Reasoning and tool items are deliberately excluded from the user-visible answer.
    messages = [
        item["content"]
        for item in data.get("output", [])
        if item.get("type") == "message"
    ]
    text = "\n".join(messages).strip()
    stats = data.get("stats", {})

    return {
        "text": text,
        "model": data.get("model_instance_id", model),
        "input_tokens": stats.get("input_tokens"),
        "output_tokens": stats.get("total_output_tokens"),
        "reasoning_output_tokens": stats.get("reasoning_output_tokens"),
        "tokens_per_second": stats.get("tokens_per_second"),
        "time_to_first_token_seconds": stats.get("time_to_first_token_seconds"),
        "model_load_time_seconds": stats.get("model_load_time_seconds"),
    }


async def generate_structured(
    *,
    model: str,
    prompt: str,
    system: str | None,
    reasoning: str | None,
    temperature: float,
    max_output_tokens: int,
    schema: dict[str, Any],
    schema_name: str = "structured_output",
) -> dict[str, Any]:
    """Generate JSON constrained by a caller-provided schema."""

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
    }
    # LM Studio's OpenAI-compatible endpoint uses reasoning_effort for gpt-oss.
    if reasoning:
        body["reasoning_effort"] = reasoning

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        response = await client.post(
            f"{settings.lm_base_url}/v1/chat/completions",
            headers=_headers(),
            json=body,
        )

    if not response.is_success:
        raise LMStudioError(
            "LM Studio structured generation returned "
            f"{response.status_code}: {response.text}"
        )

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise LMStudioError("LM Studio returned no completion choices.")

    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise LMStudioError("LM Studio returned no structured message content.")

    usage = data.get("usage") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    return {
        "text": content.strip(),
        "model": data.get("model", model),
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "reasoning_output_tokens": completion_details.get("reasoning_tokens"),
        "finish_reason": choice.get("finish_reason"),
    }


async def generate_tool_turn(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_choice: str,
    reasoning: str | None,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Request one OpenAI-compatible tool-planning or synthesis chat turn."""

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
        "stream": False,
    }
    # LM Studio's documented post-tool flow omits tools entirely for the final
    # synthesis turn. This is a stronger boundary and uses less prompt context
    # than re-advertising the tools with `tool_choice=none`.
    if tool_choice != "none":
        body["tools"] = tools
        body["tool_choice"] = tool_choice
    if reasoning:
        body["reasoning_effort"] = reasoning

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        response = await client.post(
            f"{settings.lm_base_url}/v1/chat/completions",
            headers=_headers(),
            json=body,
        )

    if not response.is_success:
        raise LMStudioError(
            f"LM Studio tool generation returned {response.status_code}: {response.text}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise LMStudioError("LM Studio tool generation returned invalid JSON.") from exc

    choices = data.get("choices") or []
    if not choices:
        raise LMStudioError("LM Studio returned no tool-generation completion choices.")

    choice = choices[0]
    message = choice.get("message") or {}
    raw_tool_calls = message.get("tool_calls") or []
    if not isinstance(raw_tool_calls, list):
        raise LMStudioError("LM Studio returned an invalid tool_calls field.")

    content = message.get("content")
    text = content if isinstance(content, str) else None
    usage = data.get("usage") or {}
    completion_details = usage.get("completion_tokens_details") or {}

    return {
        "text": text,
        "tool_calls": raw_tool_calls,
        "model": data.get("model", model),
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "reasoning_output_tokens": completion_details.get("reasoning_tokens"),
        "finish_reason": choice.get("finish_reason"),
    }


async def embed_texts(*, model: str, texts: list[str]) -> dict[str, Any]:
    """Generate dense vectors through LM Studio's OpenAI-compatible endpoint."""

    if not texts:
        raise ValueError("texts cannot be empty")

    body = {"model": model, "input": texts, "encoding_format": "float"}
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        response = await client.post(
            f"{settings.lm_base_url}/v1/embeddings",
            headers=_headers(),
            json=body,
        )

    if not response.is_success:
        raise LMStudioError(
            f"LM Studio embeddings returned {response.status_code}: {response.text}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise LMStudioError("LM Studio embeddings returned invalid JSON.") from exc

    items = payload.get("data") or []
    if len(items) != len(texts):
        raise LMStudioError(
            "LM Studio embeddings returned a different number of vectors than inputs."
        )

    ordered = sorted(items, key=lambda item: int(item.get("index", 0)))
    vectors: list[list[float]] = []
    dimension: int | None = None
    for item in ordered:
        vector = item.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise LMStudioError("LM Studio returned an empty or invalid embedding vector.")
        try:
            converted = [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise LMStudioError("LM Studio returned a non-numeric embedding vector.") from exc
        if dimension is None:
            dimension = len(converted)
        elif len(converted) != dimension:
            raise LMStudioError("LM Studio returned inconsistent embedding dimensions.")
        vectors.append(converted)

    usage = payload.get("usage") or {}
    return {
        "vectors": vectors,
        "model": str(payload.get("model") or model),
        "dimensions": dimension or 0,
        "input_tokens": usage.get("prompt_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


async def list_models() -> list[dict[str, Any]]:
    """Return LM Studio's current local model inventory."""

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        response = await client.get(
            f"{settings.lm_base_url}/api/v1/models",
            headers=_headers(),
        )

    if not response.is_success:
        raise LMStudioError(
            f"LM Studio model inventory returned {response.status_code}: {response.text}"
        )

    data = response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        models = data.get("models") or data.get("data") or []
        if isinstance(models, list):
            return models
    return []
