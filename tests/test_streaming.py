"""Regression tests for SSE framing, provider normalization, and SDK streaming helpers."""

from __future__ import annotations

import asyncio

import pytest
from taheem_ai import AI, AsyncAI
from taheem_ai.errors import AIError
from taheem_ai.streaming import SSEDecoder as ClientSSEDecoder
from taheem_ai.streaming import raise_if_stream_error

from app.lmstudio import LMStudioError
from app.main import app
from app.streaming.provider import SSEDecoder as ProviderSSEDecoder
from app.streaming.provider import normalize_provider_event
from app.streaming.sse import encode_sse


def test_streaming_route_is_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/v1/generate/stream" in paths


def test_gateway_sse_encoder_uses_named_event_and_json_type() -> None:
    encoded = encode_sse("delta", {"text": "héllo"})
    assert encoded.startswith("event: delta\n")
    assert '"type":"delta"' in encoded
    assert '"text":"héllo"' in encoded
    assert encoded.endswith("\n\n")


def test_provider_decoder_handles_multiline_json_data() -> None:
    decoder = ProviderSSEDecoder()
    assert decoder.feed_line("event: message.delta") is None
    assert decoder.feed_line('data: {"type":') is None
    assert decoder.feed_line('data: "message.delta", "content": "Hi"}') is None
    decoded = decoder.feed_line("")
    assert decoded == (
        "message.delta",
        {"type": "message.delta", "content": "Hi"},
    )


def test_reasoning_events_are_never_normalized_for_public_output() -> None:
    assert (
        normalize_provider_event(
            "reasoning.delta",
            {"type": "reasoning.delta", "content": "private chain"},
        )
        is None
    )


def test_message_delta_becomes_public_text_delta() -> None:
    event = normalize_provider_event(
        "message.delta",
        {"type": "message.delta", "content": "hello"},
    )
    assert event == {"type": "delta", "text": "hello"}


def test_chat_end_matches_nonstreaming_message_aggregation() -> None:
    event = normalize_provider_event(
        "chat.end",
        {
            "type": "chat.end",
            "result": {
                "model_instance_id": "gpt-test",
                "output": [
                    {"type": "reasoning", "content": "private"},
                    {"type": "message", "content": "first"},
                    {"type": "message", "content": "second"},
                ],
                "stats": {
                    "input_tokens": 10,
                    "total_output_tokens": 8,
                    "reasoning_output_tokens": 3,
                    "tokens_per_second": 20.0,
                    "time_to_first_token_seconds": 0.25,
                },
            },
        },
    )
    assert event is not None
    assert event["type"] == "completed"
    assert event["text"] == "first\nsecond"
    assert "private" not in event["text"]
    assert event["reasoning_output_tokens"] == 3


def test_provider_error_event_fails_closed() -> None:
    with pytest.raises(LMStudioError, match="provider exploded"):
        normalize_provider_event(
            "error",
            {
                "type": "error",
                "error": {"type": "internal_error", "message": "provider exploded"},
            },
        )


def test_client_decoder_and_inband_error_translation() -> None:
    decoder = ClientSSEDecoder()
    decoder.feed_line("event: error")
    decoder.feed_line(
        'data: {"type":"error","error":{"code":"STREAM_FAILED","message":"boom"}}'
    )
    event = decoder.feed_line("")
    assert event is not None
    with pytest.raises(AIError, match="boom"):
        raise_if_stream_error(event)


def test_sync_stream_filters_lifecycle_events(monkeypatch) -> None:
    ai = AI(api_key="test")

    def fake_events(*args, **kwargs):
        del args, kwargs
        yield {"type": "start"}
        yield {"type": "progress", "phase": "prompt_processing"}
        yield {"type": "delta", "text": "hel"}
        yield {"type": "delta", "text": "lo"}
        yield {"type": "completed", "text": "hello"}

    monkeypatch.setattr(ai, "stream_events", fake_events)
    assert "".join(ai.stream("ignored")) == "hello"


def test_async_stream_filters_lifecycle_events(monkeypatch) -> None:
    ai = AsyncAI(api_key="test")

    async def fake_events(*args, **kwargs):
        del args, kwargs
        yield {"type": "start"}
        yield {"type": "delta", "text": "39"}
        yield {"type": "delta", "text": "1"}
        yield {"type": "completed", "text": "391"}

    monkeypatch.setattr(ai, "stream_events", fake_events)

    async def collect() -> str:
        return "".join([chunk async for chunk in ai.stream("ignored")])

    assert asyncio.run(collect()) == "391"
