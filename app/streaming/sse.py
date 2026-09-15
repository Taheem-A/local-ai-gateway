"""Small helpers for the gateway-owned Server-Sent Events contract."""

from __future__ import annotations

import json
from typing import Any


def encode_sse(event_type: str, data: dict[str, Any]) -> str:
    """Encode one named SSE event with a standards-valid JSON payload."""

    payload = dict(data)
    payload.setdefault("type", event_type)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"event: {event_type}\ndata: {encoded}\n\n"
