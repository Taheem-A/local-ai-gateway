from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


def check_schema(schema: dict[str, Any]) -> None:
    """Raise ValueError when a caller supplied an invalid JSON Schema."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid JSON Schema: {exc.message}") from exc


def parse_json(text: str) -> Any:
    candidate = text.strip()

    # Defensive compatibility for models that still wrap output in a code fence.
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    return json.loads(candidate)


def validation_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))

    result: list[str] = []
    for error in errors:
        path = ".".join(str(part) for part in error.absolute_path)
        prefix = f"{path}: " if path else ""
        result.append(prefix + error.message)
    return result
