"""Prepare caller JSON Schemas and prompt hints for LM Studio constrained output."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Avoid shorthand classes such as \d in model-facing patterns. Explicit character
# ranges are more reliable in llama.cpp's JSON-Schema-to-grammar conversion path.
LOCAL_TIME_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
LOCAL_TIME_DESCRIPTION = (
    "Time in 24-hour HH:MM format. Preserve the local clock time stated in the "
    "source; do not convert timezones and do not add seconds or a timezone suffix."
)


def prepare_generation_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the model-facing schema without mutating the caller's contract.

    The gateway's public ``format: \"time\"`` means a local HH:MM clock value,
    while standard JSON Schema allows RFC 3339 full-time values with seconds and
    timezone suffixes. Model-facing time fields are therefore converted to an
    explicit pattern. Private ``x-*`` annotations are also stripped.
    """

    return _prepare_node(deepcopy(schema))


def generation_prompt_hints(schema: dict[str, Any]) -> list[str]:
    """Return natural-language canonicalization rules implied by the schema."""

    hints: list[str] = []
    _collect_hints(schema, path="", hints=hints)
    return hints


def add_generation_hints(prompt: str, schema: dict[str, Any]) -> str:
    """Append schema-derived representation requirements to a model prompt."""

    hints = generation_prompt_hints(schema)
    if not hints:
        return prompt

    rendered = "\n".join(f"- {hint}" for hint in hints)
    return (
        f"{prompt}\n\n"
        "Canonical output requirements:\n"
        f"{rendered}\n"
        "These representation requirements are mandatory."
    )


def _prepare_node(value: Any) -> Any:
    """Recursively transform one JSON-Schema node for constrained generation."""

    if isinstance(value, list):
        return [_prepare_node(item) for item in value]
    if not isinstance(value, dict):
        return value

    result: dict[str, Any] = {}
    for key, item in value.items():
        if key.startswith("x-"):
            continue
        result[key] = _prepare_node(item)

    if result.get("type") == "string" and result.get("format") == "time":
        result.pop("format", None)
        result.setdefault("pattern", LOCAL_TIME_PATTERN)

        description = str(result.get("description") or "").strip()
        result["description"] = (
            f"{description} {LOCAL_TIME_DESCRIPTION}"
            if description
            else LOCAL_TIME_DESCRIPTION
        )

    return result


def _collect_hints(value: Any, *, path: str, hints: list[str]) -> None:
    """Collect human-readable representation rules from nested schema nodes."""

    if not isinstance(value, dict):
        return

    schema_type = value.get("type")
    if schema_type == "object":
        properties = value.get("properties", {})
        if isinstance(properties, dict):
            for key, child in properties.items():
                child_path = f"{path}.{key}" if path else key
                _collect_hints(child, path=child_path, hints=hints)
        return

    if schema_type == "array":
        item_schema = value.get("items")
        if isinstance(item_schema, dict):
            child_path = f"{path}[]" if path else "[]"
            _collect_hints(item_schema, path=child_path, hints=hints)
        return

    if schema_type != "string":
        return

    field_name = path or "string value"
    fmt = value.get("format")
    normalizer = value.get("x-normalize")

    if fmt == "time":
        hints.append(f"{field_name}: {LOCAL_TIME_DESCRIPTION}")
    elif fmt == "date":
        hints.append(f"{field_name}: use calendar date format YYYY-MM-DD.")

    if normalizer == "upper":
        hints.append(f"{field_name}: use uppercase characters where applicable.")
    elif normalizer == "lower":
        hints.append(f"{field_name}: use lowercase characters where applicable.")
