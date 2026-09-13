from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class LMStudioError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.lm_api_token}",
        "Content-Type": "application/json",
    }


def _timeout() -> httpx.Timeout:
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
        raise LMStudioError(
            f"LM Studio returned {response.status_code}: {response.text}"
        )

    data = response.json()

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
    """Generate schema-constrained JSON through LM Studio's OpenAI-compatible API."""

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

    # LM Studio's OpenAI-compatible chat endpoint accepts reasoning_effort for
    # reasoning-capable models such as gpt-oss. Non-reasoning profiles pass None.
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
            f"LM Studio structured generation returned "
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


async def list_models() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        response = await client.get(
            f"{settings.lm_base_url}/api/v1/models",
            headers=_headers(),
        )

    if not response.is_success:
        raise LMStudioError(
            f"LM Studio model inventory returned "
            f"{response.status_code}: {response.text}"
        )

    data = response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        models = data.get("models") or data.get("data") or []
        if isinstance(models, list):
            return models
    return []
