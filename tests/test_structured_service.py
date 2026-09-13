import asyncio

import pytest

from app.errors import StructuredOutputError
from app.structured import service
from app.structured.schema_prep import LOCAL_TIME_PATTERN


def test_run_structured_sends_prepared_time_schema_and_prompt_hint(monkeypatch):
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
    assert sent_time_schema["pattern"] == LOCAL_TIME_PATTERN
    assert "\\d" not in sent_time_schema["pattern"]
    assert "due_time: Time in 24-hour HH:MM format" in captured["prompt"]
    assert "do not convert timezones" in captured["prompt"]
    assert result.data == {"due_time": "23:59"}
    assert result.reasoning_output_tokens == 2


def test_run_structured_canonicalizes_zero_seconds_before_validation(monkeypatch):
    async def fake_generate_structured(**kwargs):
        return {
            "text": '{"due_time":"23:59:00"}',
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

    assert result.data == {"due_time": "23:59"}
    assert result.attempts == 1


def test_run_structured_does_not_hide_timezone_conversion(monkeypatch):
    async def fake_generate_structured(**kwargs):
        return {
            "text": '{"due_time":"18:59:00Z"}',
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

    with pytest.raises(StructuredOutputError) as exc_info:
        asyncio.run(
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

    assert "18:59:00Z" in exc_info.value.details["last_output"]
    assert exc_info.value.details["validation_errors"]


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
