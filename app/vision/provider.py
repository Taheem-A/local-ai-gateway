"""LM Studio native-v1 adapter for bounded multimodal generation."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.vision.errors import (
    VisionModelError,
    VisionOutputError,
    VisionProtocolError,
    VisionProviderRejectedError,
    VisionProviderTimeoutError,
    VisionProviderUnavailableError,
    VisionRuntimeError,
)
from app.vision.images import PreparedVisionImage


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.lm_api_token}",
        "Content-Type": "application/json",
    }


def _provider_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"raw": response.text[:2000]}
    return payload if isinstance(payload, dict) else {"raw": str(payload)[:2000]}


def _provider_message(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "").strip()
    return str(payload.get("message") or "").strip()


def _known_runtime_advisory(message: str) -> dict[str, Any] | None:
    lowered = message.casefold()
    if "terminated" in lowered and "gemma-4" in settings.vision_model.casefold():
        return {
            "id": "gemma4-physical-batch",
            "summary": "Gemma 4 vision can terminate when LM Studio's physical batch is too small for image tokens.",
            "suggested_action": (
                "Set the Gemma 4 model's Physical Batch Size to 2048 in LM Studio, "
                "save the per-model load settings, unload the model, and retry."
            ),
        }
    return None


def _raise_for_provider_failure(response: httpx.Response) -> None:
    if response.is_success:
        return
    payload = _provider_payload(response)
    message = _provider_message(payload) or f"LM Studio returned HTTP {response.status_code}."
    details: dict[str, Any] = {
        "provider": "lmstudio",
        "provider_status": response.status_code,
        "provider_error": payload,
        "model": settings.vision_model,
        "retryable": response.status_code in {408, 409, 425, 429, 500, 502, 503, 504},
    }

    if response.status_code == 404:
        raise VisionModelError(
            "LM Studio could not resolve the configured vision model.",
            details=details,
        )
    if response.status_code == 429:
        raise VisionProviderUnavailableError(
            "LM Studio is busy or rate-limiting the local vision request.",
            details=details,
        )
    if response.status_code in {400, 409, 413, 422}:
        raise VisionProviderRejectedError(
            "LM Studio rejected the gateway's multimodal request.",
            details=details,
        )
    if response.status_code >= 500:
        advisory = _known_runtime_advisory(message)
        if advisory is not None:
            details["advisory"] = advisory
        if "terminated" in message.casefold():
            raise VisionRuntimeError(
                "The local vision runtime terminated while processing the request.",
                details=details,
            )
        raise VisionRuntimeError(
            "LM Studio failed while running the local vision model.",
            details=details,
        )
    raise VisionProviderRejectedError(
        f"LM Studio returned an unexpected HTTP {response.status_code} response.",
        details=details,
    )


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
    input_items.extend({"type": "image", "data_url": image.data_url} for image in images)
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

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.lm_timeout_seconds)) as client:
            response = await client.post(
                f"{settings.lm_base_url}/api/v1/chat",
                headers=_headers(),
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise VisionProviderTimeoutError(
            "LM Studio did not finish the vision request before the gateway timeout.",
            details={
                "provider": "lmstudio",
                "model": settings.vision_model,
                "timeout_seconds": settings.lm_timeout_seconds,
                "retryable": True,
            },
        ) from exc
    except httpx.RequestError as exc:
        raise VisionProviderUnavailableError(
            "The gateway could not reach LM Studio for vision inference.",
            details={
                "provider": "lmstudio",
                "model": settings.vision_model,
                "exception": type(exc).__name__,
                "retryable": True,
            },
        ) from exc

    _raise_for_provider_failure(response)

    try:
        data = response.json()
    except ValueError as exc:
        raise VisionProtocolError(
            "LM Studio returned non-JSON data for a successful vision request.",
            details={"provider": "lmstudio", "model": settings.vision_model},
        ) from exc
    if not isinstance(data, dict):
        raise VisionProtocolError(
            "LM Studio returned an unexpected vision response shape.",
            details={"provider": "lmstudio", "model": settings.vision_model},
        )

    output = data.get("output")
    if not isinstance(output, list):
        raise VisionProtocolError(
            "LM Studio's vision response did not contain an output list.",
            details={"provider": "lmstudio", "model": settings.vision_model},
        )

    messages = [
        item.get("content", "")
        for item in output
        if isinstance(item, dict) and item.get("type") == "message"
    ]
    text = "\n".join(part for part in messages if isinstance(part, str)).strip()
    if not text:
        raise VisionOutputError(
            "The local vision model completed without visible response text.",
            details={"provider": "lmstudio", "model": settings.vision_model},
        )

    stats = data.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {}
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
