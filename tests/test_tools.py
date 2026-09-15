"""Regression tests for tool schemas, history validation, and model-call normalization."""

from __future__ import annotations

import asyncio

import pytest

from app.errors import (
    ToolCallError,
    ToolCallRequiredError,
    ToolHistoryError,
    ToolSchemaError,
)
from app.schemas import ToolTurnRequest
from app.tools import service


def _weather_tool(*, risk: str = "read") -> dict:
    return {
        "name": "get_weather",
        "description": "Get the current weather for one city.",
        "risk": risk,
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
            "additionalProperties": False,
        },
    }


def _request(**overrides) -> ToolTurnRequest:
    payload = {
        "messages": [{"role": "user", "content": "What is the weather in Toronto?"}],
        "tools": [_weather_tool()],
        "tool_choice": "auto",
    }
    payload.update(overrides)
    return ToolTurnRequest.model_validate(payload)


def test_valid_tool_call_is_schema_checked_and_risk_annotated(monkeypatch):
    captured: dict = {}

    async def fake_provider(**kwargs):
        captured.update(kwargs)
        return {
            "text": None,
            "tool_calls": [
                {
                    "id": "call_weather",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city":"Toronto"}',
                    },
                }
            ],
            "model": "gpt-test",
            "input_tokens": 20,
            "output_tokens": 8,
            "reasoning_output_tokens": 3,
            "finish_reason": "tool_calls",
        }

    monkeypatch.setattr(service, "generate_tool_turn", fake_provider)
    result = asyncio.run(
        service.run_tool_turn(request=_request(), model="gpt-test", reasoning="low")
    )

    assert result.status == "tool_calls"
    assert result.tool_calls[0].name == "get_weather"
    assert result.tool_calls[0].arguments == {"city": "Toronto"}
    assert result.tool_calls[0].risk == "read"
    assert result.assistant_message.tool_calls[0].id == "call_weather"
    assert captured["tool_choice"] == "auto"
    assert "untrusted external data" in captured["messages"][0]["content"]
    assert "risk" not in captured["tools"][0]["function"]


def test_model_cannot_request_unknown_tool(monkeypatch):
    async def fake_provider(**kwargs):
        del kwargs
        return {
            "text": None,
            "tool_calls": [
                {
                    "id": "call_bad",
                    "function": {"name": "delete_everything", "arguments": "{}"},
                }
            ],
            "model": "gpt-test",
            "input_tokens": 1,
            "output_tokens": 1,
            "reasoning_output_tokens": 0,
            "finish_reason": "tool_calls",
        }

    monkeypatch.setattr(service, "generate_tool_turn", fake_provider)
    with pytest.raises(ToolCallError, match="not advertised"):
        asyncio.run(service.run_tool_turn(request=_request(), model="gpt-test", reasoning=None))


def test_model_arguments_must_match_tool_schema(monkeypatch):
    async def fake_provider(**kwargs):
        del kwargs
        return {
            "text": None,
            "tool_calls": [
                {
                    "id": "call_weather",
                    "function": {"name": "get_weather", "arguments": '{"city":42}'},
                }
            ],
            "model": "gpt-test",
            "input_tokens": 1,
            "output_tokens": 1,
            "reasoning_output_tokens": 0,
            "finish_reason": "tool_calls",
        }

    monkeypatch.setattr(service, "generate_tool_turn", fake_provider)
    with pytest.raises(ToolCallError) as exc_info:
        asyncio.run(service.run_tool_turn(request=_request(), model="gpt-test", reasoning=None))

    assert "validation_errors" in exc_info.value.details


def test_external_schema_refs_are_rejected_before_provider_call():
    request = _request(
        tools=[
            {
                "name": "lookup",
                "description": "Look something up.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"$ref": "https://example.com/schema.json"}},
                },
            }
        ]
    )

    with pytest.raises(ToolSchemaError, match="self-contained"):
        asyncio.run(service.run_tool_turn(request=request, model="gpt-test", reasoning=None))


def test_tool_history_requires_matching_results():
    request = _request(
        messages=[
            {"role": "user", "content": "Check Toronto."},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_weather",
                        "name": "get_weather",
                        "arguments": {"city": "Toronto"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_weather",
                "name": "get_weather",
                "content": {"temperature_c": 20},
            },
            {"role": "user", "content": "Thanks."},
        ]
    )

    validators = service._tool_validators(request.tools)
    service._validate_history(request.messages, validators)

    bad = _request(
        messages=[
            {
                "role": "tool",
                "tool_call_id": "missing",
                "name": "get_weather",
                "content": {"temperature_c": 20},
            }
        ]
    )
    with pytest.raises(ToolHistoryError, match="outstanding"):
        service._validate_history(bad.messages, service._tool_validators(bad.tools))


def test_required_tool_choice_fails_closed_when_model_returns_only_text(monkeypatch):
    async def fake_provider(**kwargs):
        del kwargs
        return {
            "text": "I think it is sunny.",
            "tool_calls": [],
            "model": "gpt-test",
            "input_tokens": 1,
            "output_tokens": 4,
            "reasoning_output_tokens": 0,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(service, "generate_tool_turn", fake_provider)
    with pytest.raises(ToolCallRequiredError):
        asyncio.run(
            service.run_tool_turn(
                request=_request(tool_choice="required"),
                model="gpt-test",
                reasoning=None,
            )
        )


def test_text_only_turn_remains_a_normal_completed_response(monkeypatch):
    async def fake_provider(**kwargs):
        del kwargs
        return {
            "text": "Hello!",
            "tool_calls": [],
            "model": "gpt-test",
            "input_tokens": 1,
            "output_tokens": 2,
            "reasoning_output_tokens": 0,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(service, "generate_tool_turn", fake_provider)
    result = asyncio.run(
        service.run_tool_turn(request=_request(), model="gpt-test", reasoning=None)
    )

    assert result.status == "completed"
    assert result.text == "Hello!"
    assert result.assistant_message.content == "Hello!"
