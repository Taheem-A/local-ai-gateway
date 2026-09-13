import asyncio

import pytest

from app.errors import StructuredOutputError
from app.structured import service


def test_run_structured_sends_prepared_time_schema(monkeypatch):
    captured = {}

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return {
            "text": '{"due_time":"23:59"}',
            "model": "test-model",
            "input_tokens": 10,
            "output_tokens": 5,
            "reasoning_output_tokens": 2,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(service, "generate_structured", fake_generate_structured)

    schema = {
        "type": "object",
        "properties": {"due_time": {"type": "string", "format": "time"}},
        "required": ["due_time"],
        "additionalProperties": False,
    }

    result = asyncio.run(
        service.run_structured(
            model="test-model",
            prompt="Due at 11:59 PM",
            schema=schema,
            system=None,
            reasoning="medium",
            temperature=0.0,
            max_output_tokens=512,
            max_attempts=1,
        )
    )

    sent_time_schema = captured["schema"]["properties"]["due_time"]
    assert "format" not in sent_time_schema
    assert sent_time_schema["pattern"].endswith("[0-5]\\d$")
    assert result.data == {"due_time": "23:59"}
    assert result.reasoning_output_tokens == 2


def test_empty_length_limited_response_has_specific_diagnostics(monkeypatch):
    async def fake_generate_structured(**kwargs):
        return {
            "text": "",
            "model": "test-model",
            "input_tokens": 20,
            "output_tokens": 512,
            "reasoning_output_tokens": 510,
            "finish_reason": "length",
        }

    monkeypatch.setattr(service, "generate_structured", fake_generate_structured)

    schema = {
        "type": "object",
        "properties": {"label": {"type": "string", "enum": ["a", "b"]}},
        "required": ["label"],
        "additionalProperties": False,
    }

    with pytest.raises(StructuredOutputError) as exc_info:
        asyncio.run(
            service.run_structured(
                model="test-model",
                prompt="Classify this",
                schema=schema,
                system=None,
                reasoning="medium",
                temperature=0.0,
                max_output_tokens=512,
                max_attempts=1,
            )
        )

    details = exc_info.value.details
    assert details["finish_reason"] == "length"
    assert details["reasoning_output_tokens"] == 510
    assert "output-token budget" in details["validation_errors"][0]
