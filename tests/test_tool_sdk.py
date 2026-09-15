"""Regression tests for caller-side tool registration and bounded SDK execution."""

from __future__ import annotations

import asyncio

import pytest
from taheem_ai import AI
from taheem_ai.tools import (
    ToolExecutionError,
    ToolPermissionError,
    ToolRegistry,
    ToolRegistryError,
)


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
        "additionalProperties": False,
    }


def test_registry_validates_arguments_before_handler_runs():
    seen: list[str] = []
    registry = ToolRegistry().register(
        name="get_weather",
        description="Get weather for one city.",
        parameters=_schema(),
        handler=lambda city: seen.append(city) or {"city": city, "temperature_c": 20},
    )

    result = registry.execute(
        {"name": "get_weather", "arguments": {"city": "Toronto"}}
    )
    assert result["temperature_c"] == 20
    assert seen == ["Toronto"]

    with pytest.raises(ToolExecutionError, match="argument validation failed"):
        registry.execute({"name": "get_weather", "arguments": {"city": 42}})
    assert seen == ["Toronto"]


def test_registry_blocks_write_and_destructive_tools_by_default():
    registry = ToolRegistry().register(
        name="create_reminder",
        description="Create a reminder.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=lambda text: {"created": text},
        risk="write",
    )

    call = {"name": "create_reminder", "arguments": {"text": "Study"}}
    with pytest.raises(ToolPermissionError):
        registry.execute(call)

    assert registry.execute(call, allowed_risks={"read", "write"}) == {"created": "Study"}


def test_registry_rejects_duplicate_names():
    registry = ToolRegistry().register(
        name="lookup",
        description="Look up a value.",
        parameters={"type": "object", "properties": {}},
        handler=lambda: {},
    )
    with pytest.raises(ToolRegistryError, match="already registered"):
        registry.register(
            name="lookup",
            description="Another lookup.",
            parameters={"type": "object", "properties": {}},
            handler=lambda: {},
        )


def test_async_registry_awaits_async_handlers():
    async def handler(city: str):
        return {"city": city, "ok": True}

    registry = ToolRegistry().register(
        name="get_weather",
        description="Get weather.",
        parameters=_schema(),
        handler=handler,
    )
    result = asyncio.run(
        registry.execute_async(
            {"name": "get_weather", "arguments": {"city": "Ajax"}}
        )
    )
    assert result == {"city": "Ajax", "ok": True}


def test_run_tools_once_executes_one_round_then_forces_text(monkeypatch):
    executions: list[str] = []
    registry = ToolRegistry().register(
        name="get_weather",
        description="Get weather.",
        parameters=_schema(),
        handler=lambda city: executions.append(city) or {"temperature_c": 20},
    )
    ai = AI(api_key="test-key")
    choices: list[str] = []

    def fake_turn(messages, tools, **kwargs):
        del tools
        choices.append(kwargs["tool_choice"])
        if kwargs["tool_choice"] == "auto":
            return {
                "status": "tool_calls",
                "text": None,
                "tool_calls": [
                    {
                        "id": "call_weather",
                        "name": "get_weather",
                        "arguments": {"city": "Toronto"},
                        "risk": "read",
                    }
                ],
                "assistant_message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_weather",
                            "name": "get_weather",
                            "arguments": {"city": "Toronto"},
                        }
                    ],
                },
            }
        assert messages[-1]["role"] == "tool"
        assert messages[-1]["content"] == {"temperature_c": 20}
        return {
            "status": "completed",
            "text": "Toronto is 20 C.",
            "tool_calls": [],
            "assistant_message": {
                "role": "assistant",
                "content": "Toronto is 20 C.",
                "tool_calls": [],
            },
        }

    monkeypatch.setattr(ai, "tool_turn", fake_turn)
    result = ai.run_tools_once("What is Toronto weather?", registry)

    assert result.text == "Toronto is 20 C."
    assert executions == ["Toronto"]
    assert choices == ["auto", "none"]
