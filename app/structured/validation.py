"""Strict JSON parsing and Draft 2020-12 validation for structured responses."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date", raises=ValueError)
def _is_date(value: object) -> bool:
    """Validate the gateway's canonical ISO calendar-date representation."""

    if not isinstance(value, str):
        return True
    datetime.strptime(value, "%Y-%m-%d")
    return True


@FORMAT_CHECKER.checks("time", raises=ValueError)
def _is_time(value: object) -> bool:
    """Validate the gateway's canonical local 24-hour HH:MM representation."""

    if not isinstance(value, str):
        return True
    datetime.strptime(value, "%H:%M")
    return True


def check_schema(schema: dict[str, Any]) -> None:
    """Raise ValueError when a caller supplies an invalid JSON Schema."""

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid JSON Schema: {exc.message}") from exc


def parse_json(text: str) -> Any:
    """Parse one JSON value, defensively stripping one surrounding Markdown fence."""

    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    return json.loads(candidate)


def validation_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    """Return stable path-prefixed validation errors for repair prompts and clients."""

    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))

    result: list[str] = []
    for error in errors:
        path = ".".join(str(part) for part in error.absolute_path)
        prefix = f"{path}: " if path else ""
        result.append(prefix + error.message)
    return result
