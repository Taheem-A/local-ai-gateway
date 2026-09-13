from __future__ import annotations

from copy import deepcopy
from typing import Any


# Avoid regex shorthand classes such as \d here. LM Studio's GGUF structured
# output is backed by llama.cpp's JSON-Schema-to-grammar conversion, and explicit
# character ranges are more reliably supported by that conversion path.
LOCAL_TIME_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
LOCAL_TIME_DESCRIPTION = (
    "Time in 24-hour HH:MM format. Preserve the local clock time stated in the "
    "source; do not convert timezones and do not add seconds or a timezone suffix."
)


def prepare_generation_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the schema LM Studio should see during constrained generation.

    The public gateway accepts ``format: \"time\"`` as a convenience for a local
    HH:MM clock value. Standard JSON Schema defines ``time`` as RFC 3339 full-time,
    which permits values such as ``18:59:00Z``. That is not what our extraction API
    means when it asks for an assignment due time.

    To keep the external API convenient while avoiding a conflict between LM
    Studio's structured-output engine and the gateway validator, we translate
    string/time fields to an explicit HH:MM pattern before sending the schema to
    the model. The original caller schema is still used for gateway-side
    normalization and validation.

    Private ``x-*`` gateway annotations are stripped from the schema sent to the
    model because they are not part of JSON Schema and are only meaningful to the
    gateway.
    """

    prepared = deepcopy(schema)
    return _prepare_node(prepared)


def generation_prompt_hints(schema: dict[str, Any]) -> list[str]:
    """Describe representation rules that constrained decoding alone cannot teach.

    Grammar-based structured output constrains token shapes, but the model does not
    necessarily receive JSON Schema descriptions as natural-language instructions.
    These hints make gateway-specific canonical representations explicit in the
    prompt as well as in the model-facing schema.
    """

    hints: list[str] = []
    _collect_hints(schema, path="", hints=hints)
    return hints


def add_generation_hints(prompt: str, schema: dict[str, Any]) -> str:
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
        # RFC 3339 `time` and our canonical local HH:MM representation are
        # different contracts. The constrained decoder must see the exact
        # representation our API wants.
        result.pop("format", None)
        result.setdefault("pattern", LOCAL_TIME_PATTERN)

        description = str(result.get("description") or "").strip()
        if description:
            result["description"] = f"{description} {LOCAL_TIME_DESCRIPTION}"
        else:
            result["description"] = LOCAL_TIME_DESCRIPTION

    return result


def _collect_hints(value: Any, *, path: str, hints: list[str]) -> None:
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
