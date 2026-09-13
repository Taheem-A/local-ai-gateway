from __future__ import annotations

from datetime import datetime
from typing import Any

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
)

_TIME_FORMATS = (
    "%H:%M",
    "%I:%M %p",
    "%I:%M%p",
)


def _normalize_date(value: str) -> str:
    stripped = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return value


def _normalize_time(value: str) -> str:
    stripped = value.strip().upper()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).strftime("%H:%M")
        except ValueError:
            pass
    return value


def normalize_instance(value: Any, schema: dict[str, Any]) -> Any:
    """Apply conservative, schema-directed normalization.

    This intentionally never changes a value to a different factual value. It only
    canonicalizes equivalent representations, such as 11:59 PM -> 23:59.
    """

    schema_type = schema.get("type")

    if schema_type == "object" and isinstance(value, dict):
        properties = schema.get("properties", {})
        return {
            key: normalize_instance(item, properties.get(key, {}))
            for key, item in value.items()
        }

    if schema_type == "array" and isinstance(value, list):
        item_schema = schema.get("items", {})
        return [normalize_instance(item, item_schema) for item in value]

    if schema_type == "integer" and isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("+-").isdigit():
            return int(stripped)

    if schema_type == "number" and isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value

    if schema_type == "string" and isinstance(value, str):
        result = value.strip()
        fmt = schema.get("format")
        normalizer = schema.get("x-normalize")

        if fmt == "date":
            result = _normalize_date(result)
        elif fmt == "time":
            result = _normalize_time(result)

        if normalizer == "upper":
            result = result.upper()
        elif normalizer == "lower":
            result = result.lower()
        elif normalizer == "strip":
            result = result.strip()

        return result

    return value
