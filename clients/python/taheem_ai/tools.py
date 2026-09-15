"""Caller-side tool registration, validation, and bounded execution helpers."""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

ToolRisk = Literal["read", "write", "destructive"]
ToolHandler = Callable[..., Any]
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FORMAT_CHECKER = FormatChecker()


class ToolRegistryError(RuntimeError):
    """Base error for local SDK tool registration/execution failures."""


class ToolPermissionError(ToolRegistryError):
    """Raised before a handler runs when its declared risk is not authorized."""


class ToolExecutionError(ToolRegistryError):
    """Raised when local validation or a tool handler fails."""


@dataclass(frozen=True)
class ToolSpec:
    """One application-owned callable and the model-visible schema describing it."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    risk: ToolRisk = "read"

    def public_definition(self) -> dict[str, Any]:
        """Return the serializable definition sent to the gateway."""

        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "risk": self.risk,
        }


@dataclass(frozen=True)
class ToolRunResult:
    """Result of the SDK's intentionally single execution round."""

    text: str
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    first_turn: dict[str, Any]
    final_turn: dict[str, Any]


def _validate_spec(spec: ToolSpec) -> Draft202012Validator:
    if not _TOOL_NAME.fullmatch(spec.name):
        raise ToolRegistryError(
            "Tool names must use lowercase snake_case and start with a letter."
        )
    if not spec.description.strip():
        raise ToolRegistryError("Tool descriptions cannot be blank.")
    if spec.parameters.get("type") != "object":
        raise ToolRegistryError("Tool parameter schemas must have type='object'.")
    try:
        Draft202012Validator.check_schema(spec.parameters)
    except SchemaError as exc:
        raise ToolRegistryError(f"Invalid schema for tool '{spec.name}': {exc.message}") from exc
    return Draft202012Validator(spec.parameters, format_checker=_FORMAT_CHECKER)


def _ensure_jsonable(value: Any, *, tool_name: str) -> Any:
    """Require explicit JSON-safe tool results before they are returned to the model."""

    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(
            f"Tool '{tool_name}' returned a value that is not JSON serializable."
        ) from exc
    return value


class ToolRegistry:
    """Application-owned registry; registering a handler is the execution authority."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._validators: dict[str, Draft202012Validator] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
        risk: ToolRisk = "read",
    ) -> "ToolRegistry":
        """Register one callable and fail early on duplicate names or invalid schemas."""

        if name in self._tools:
            raise ToolRegistryError(f"Tool '{name}' is already registered.")
        spec = ToolSpec(name, description, parameters, handler, risk)
        validator = _validate_spec(spec)
        self._tools[name] = spec
        self._validators[name] = validator
        return self

    def definitions(self) -> list[dict[str, Any]]:
        """Return definitions suitable for `AI.tool_turn(...)`."""

        return [spec.public_definition() for spec in self._tools.values()]

    def _prepare_call(
        self,
        call: dict[str, Any],
        allowed_risks: set[ToolRisk] | frozenset[ToolRisk],
    ) -> tuple[ToolSpec, dict[str, Any]]:
        name = call.get("name")
        if not isinstance(name, str) or name not in self._tools:
            raise ToolExecutionError(f"Tool call references unknown tool: {name!r}")

        spec = self._tools[name]
        if spec.risk not in allowed_risks:
            raise ToolPermissionError(
                f"Tool '{name}' is declared '{spec.risk}' and is not allowed by this execution policy."
            )

        arguments = call.get("arguments")
        if not isinstance(arguments, dict):
            raise ToolExecutionError(f"Tool '{name}' arguments must be a JSON object.")

        errors = sorted(
            self._validators[name].iter_errors(arguments),
            key=lambda error: list(error.path),
        )
        if errors:
            details = "; ".join(error.message for error in errors)
            raise ToolExecutionError(f"Tool '{name}' argument validation failed: {details}")
        return spec, arguments

    def execute(
        self,
        call: dict[str, Any],
        *,
        allowed_risks: set[ToolRisk] | frozenset[ToolRisk] = frozenset({"read"}),
    ) -> Any:
        """Execute one authorized synchronous handler after local schema validation."""

        spec, arguments = self._prepare_call(call, allowed_risks)
        try:
            result = spec.handler(**arguments)
        except Exception as exc:
            raise ToolExecutionError(f"Tool '{spec.name}' failed: {exc}") from exc
        if inspect.isawaitable(result):
            raise ToolExecutionError(
                f"Tool '{spec.name}' returned an awaitable; use AsyncAI/run_tools_once instead."
            )
        return _ensure_jsonable(result, tool_name=spec.name)

    async def execute_async(
        self,
        call: dict[str, Any],
        *,
        allowed_risks: set[ToolRisk] | frozenset[ToolRisk] = frozenset({"read"}),
    ) -> Any:
        """Execute one authorized handler, awaiting async callables when necessary."""

        spec, arguments = self._prepare_call(call, allowed_risks)
        try:
            result = spec.handler(**arguments)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            raise ToolExecutionError(f"Tool '{spec.name}' failed: {exc}") from exc
        return _ensure_jsonable(result, tool_name=spec.name)
