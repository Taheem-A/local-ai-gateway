"""Shared SSE decoding helpers for the synchronous and asynchronous SDK clients."""

from __future__ import annotations

import json
from typing import Any

import httpx

from taheem_ai.errors import AIError


class SSEDecoder:
    """Decode the gateway's named JSON Server-Sent Events one line at a time."""

    def __init__(self) -> None:
        self._event_name: str | None = None
        self._data_lines: list[str] = []

    def feed_line(self, line: str) -> dict[str, Any] | None:
        """Consume one line and return a complete event payload when available."""

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

    def finish(self) -> dict[str, Any] | None:
        """Flush a final event if the stream omitted its trailing blank line."""

        return self._dispatch()

    def _dispatch(self) -> dict[str, Any] | None:
        if not self._data_lines:
            self._event_name = None
            return None

        event_name = self._event_name
        raw = "\n".join(self._data_lines)
        self._event_name = None
        self._data_lines = []

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIError("STREAM_PROTOCOL_ERROR", "Gateway stream returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise AIError("STREAM_PROTOCOL_ERROR", "Gateway stream returned a non-object event.")
        if event_name and not payload.get("type"):
            payload["type"] = event_name
        return payload


def response_error(response: httpx.Response) -> AIError:
    """Translate a completed non-success HTTP response into the SDK error type."""

    try:
        payload = response.json()
        error = payload.get("error", {})
    except (ValueError, TypeError):
        error = {}
    return AIError(
        error.get("code", f"HTTP_{response.status_code}"),
        error.get("message", response.text or "Gateway request failed."),
        error.get("details"),
    )


def raise_if_stream_error(event: dict[str, Any]) -> None:
    """Raise AIError for the gateway's in-band error event."""

    if event.get("type") != "error":
        return
    error = event.get("error")
    if not isinstance(error, dict):
        raise AIError("STREAM_FAILED", "The generation stream failed.")
    raise AIError(
        str(error.get("code") or "STREAM_FAILED"),
        str(error.get("message") or "The generation stream failed."),
        error.get("details"),
    )
