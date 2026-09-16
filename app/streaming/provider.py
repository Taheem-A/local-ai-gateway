"""Normalize LM Studio's native SSE stream into gateway-owned generation events."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.lmstudio import LMStudioError


class SSEDecoder:
    """Incrementally decode named Server-Sent Events from text lines."""

    def __init__(self) -> None:
        self._event_name: str | None = None
        self._data_lines: list[str] = []

    def feed_line(self, line: str) -> tuple[str | None, dict[str, Any]] | None:
        """Consume one decoded line and return a complete JSON SSE event if ready."""

        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return None

        field, separator, value = line.partition(":")
        if not separator:
            return None
        if value.startswith(" "):
            value = value[1:]

        if field == "event":
            self._event_name = value
        elif field == "data":
            self._data_lines.append(value)
        return None

    def finish(self) -> tuple[str | None, dict[str, Any]] | None:
        """Flush one final event when a provider omits the trailing blank line."""

        return self._dispatch()

    def _dispatch(self) -> tuple[str | None, dict[str, Any]] | None:
        if not self._data_lines:
            self._event_name = None
            return None

        event_name = self._event_name
        raw_data = "\n".join(self._data_lines)
        self._event_name = None
        self._data_lines = []

        if raw_data == "[DONE]":
            return None
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise LMStudioError("LM Studio streaming returned invalid SSE JSON.") from exc
        if not isinstance(payload, dict):
            raise LMStudioError("LM Studio streaming returned a non-object SSE payload.")
        return event_name, payload


def normalize_provider_event(
    event_name: str | None,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Map one LM Studio event to the stable subset exposed by the gateway."""

    event_type = str(payload.get("type") or event_name or "")

    # Hidden reasoning must never become part of the public streaming contract.
    if event_type in {
        "chat.start",
        "message.start",
        "message.end",
        "reasoning.start",
        "reasoning.delta",
        "reasoning.end",
    }:
        return None

    if event_type == "model_load.start":
        return {
            "type": "progress",
            "phase": "model_loading",
            "state": "started",
        }
    if event_type == "model_load.progress":
        progress = payload.get("progress")
        return {
            "type": "progress",
            "phase": "model_loading",
            "state": "running",
            "progress": float(progress) if isinstance(progress, (int, float)) else None,
        }
    if event_type == "model_load.end":
        load_time = payload.get("load_time_seconds")
        return {
            "type": "progress",
            "phase": "model_loading",
            "state": "completed",
            "progress": 1.0,
            "model_load_time_seconds": (
                float(load_time) if isinstance(load_time, (int, float)) else None
            ),
        }

    if event_type == "prompt_processing.start":
        return {
            "type": "progress",
            "phase": "prompt_processing",
            "state": "started",
        }
    if event_type == "prompt_processing.progress":
        progress = payload.get("progress")
        return {
            "type": "progress",
            "phase": "prompt_processing",
            "state": "running",
            "progress": float(progress) if isinstance(progress, (int, float)) else None,
        }
    if event_type == "prompt_processing.end":
        return {
            "type": "progress",
            "phase": "prompt_processing",
            "state": "completed",
            "progress": 1.0,
        }

    if event_type == "message.delta":
        content = payload.get("content")
        if isinstance(content, str) and content:
            return {"type": "delta", "text": content}
        return None

    if event_type == "error":
        error = payload.get("error") or {}
        error_type = error.get("type") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        detail = f" ({error_type})" if error_type else ""
        raise LMStudioError(
            f"LM Studio stream error{detail}: {message or 'unknown provider error'}"
        )

    if event_type == "chat.end":
        result = payload.get("result")
        if not isinstance(result, dict):
            raise LMStudioError("LM Studio stream ended without an aggregated result.")

        output = result.get("output") or []
        if not isinstance(output, list):
            raise LMStudioError("LM Studio stream returned an invalid aggregated output.")
        messages = [
            item.get("content")
            for item in output
            if isinstance(item, dict)
            and item.get("type") == "message"
            and isinstance(item.get("content"), str)
        ]
        text = "\n".join(messages).strip()
        stats = result.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        return {
            "type": "completed",
            "text": text,
            "model": str(result.get("model_instance_id") or ""),
            "input_tokens": stats.get("input_tokens"),
            "output_tokens": stats.get("total_output_tokens"),
            "reasoning_output_tokens": stats.get("reasoning_output_tokens"),
            "tokens_per_second": stats.get("tokens_per_second"),
            "time_to_first_token_seconds": stats.get("time_to_first_token_seconds"),
            "model_load_time_seconds": stats.get("model_load_time_seconds"),
        }

    # LM Studio may add new lifecycle events over time. Unknown provider events
    # are intentionally ignored rather than becoming accidental public API.
    return None


async def stream_generate(
    *,
    model: str,
    prompt: str,
    system: str | None,
    reasoning: str | None,
    temperature: float,
    max_output_tokens: int,
) -> AsyncIterator[dict[str, Any]]:
    """Yield normalized free-form generation events from LM Studio's native SSE API."""

    body: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "context_length": settings.default_context_length,
        "store": False,
        "stream": True,
    }
    if system:
        body["system_prompt"] = system
    if reasoning:
        body["reasoning"] = reasoning

    headers = {
        "Authorization": f"Bearer {settings.lm_api_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    timeout = httpx.Timeout(settings.lm_timeout_seconds)
    decoder = SSEDecoder()
    completed = False

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.lm_base_url}/api/v1/chat",
                headers=headers,
                json=body,
            ) as response:
                if not response.is_success:
                    raw = await response.aread()
                    detail = raw.decode("utf-8", errors="replace")
                    raise LMStudioError(
                        f"LM Studio returned {response.status_code}: {detail}"
                    )

                async for line in response.aiter_lines():
                    decoded = decoder.feed_line(line)
                    if decoded is None:
                        continue
                    normalized = normalize_provider_event(*decoded)
                    if normalized is None:
                        continue
                    if normalized["type"] == "completed":
                        completed = True
                        if not normalized["model"]:
                            normalized["model"] = model
                    yield normalized

                trailing = decoder.finish()
                if trailing is not None:
                    normalized = normalize_provider_event(*trailing)
                    if normalized is not None:
                        if normalized["type"] == "completed":
                            completed = True
                            if not normalized["model"]:
                                normalized["model"] = model
                        yield normalized
    except LMStudioError:
        raise
    except httpx.HTTPError as exc:
        raise LMStudioError(f"LM Studio streaming request failed: {exc}") from exc

    if not completed:
        raise LMStudioError("LM Studio streaming ended without a chat.end event.")
