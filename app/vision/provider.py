"""LM Studio native-v1 adapter for bounded multimodal generation."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.lmstudio import LMStudioError
from app.vision.images import PreparedVisionImage


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.lm_api_token}",
        "Content-Type": "application/json",
    }


async def generate_vision(
    *,
    prompt: str,
    images: list[PreparedVisionImage],
    system: str | None,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    """Send text plus verified image data URLs through LM Studio's native v1 chat API."""

    input_items: list[dict[str, str]] = [{"type": "text", "content": prompt}]
    input_items.extend(
        {"type": "image", "data_url": image.data_url}
        for image in images
    )
    body: dict[str, Any] = {
        "model": settings.vision_model,
        "input": input_items,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "context_length": settings.default_context_length,
        "stream": False,
        "store": False,
    }
    if system:
        body["system_prompt"] = system

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.lm_timeout_seconds)) as client:
        response = await client.post(
            f"{settings.lm_base_url}/api/v1/chat",
            headers=_headers(),
            json=body,
        )

    if not response.is_success:
        raise LMStudioError(
            f"LM Studio vision generation returned {response.status_code}: {response.text}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise LMStudioError("LM Studio vision generation returned invalid JSON.") from exc

    messages = [
        item.get("content", "")
        for item in data.get("output", [])
        if isinstance(item, dict) and item.get("type") == "message"
    ]
    text = "\n".join(part for part in messages if isinstance(part, str)).strip()
    if not text:
        raise LMStudioError("LM Studio returned no visible vision response text.")

    stats = data.get("stats") or {}
    return {
        "text": text,
        "model": str(data.get("model_instance_id") or settings.vision_model),
        "input_tokens": stats.get("input_tokens"),
        "output_tokens": stats.get("total_output_tokens"),
        "reasoning_output_tokens": stats.get("reasoning_output_tokens"),
        "tokens_per_second": stats.get("tokens_per_second"),
        "time_to_first_token_seconds": stats.get("time_to_first_token_seconds"),
        "model_load_time_seconds": stats.get("model_load_time_seconds"),
    }
