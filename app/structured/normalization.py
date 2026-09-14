"""Conservative schema-directed normalization for structured model output."""

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
_TIME_FORMATS = ("%H:%M", "%I:%M %p", "%I:%M%p")
_ZERO_SECOND_TIME_FORMATS = ("%H:%M:%S", "%I:%M:%S %p", "%I:%M:%S%p")


def _normalize_date(value: str) -> str:
    """Canonicalize supported unambiguous English dates to ISO YYYY-MM-DD."""

    stripped = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return value


def _normalize_time(value: str) -> str:
    """Canonicalize equivalent local clock representations to HH:MM.

    A seconds component is removed only when it is exactly ``00`` and no timezone
    suffix/offset is present. This preserves information and prevents normalization
    from hiding an incorrect timezone conversion.
    """

    stripped = value.strip().upper()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).strftime("%H:%M")
        except ValueError:
            pass

    for fmt in _ZERO_SECOND_TIME_FORMATS:
        try:
            parsed = datetime.strptime(stripped, fmt)
        except ValueError:
            continue
        if parsed.second == 0:
            return parsed.strftime("%H:%M")

    return value


def normalize_instance(value: Any, schema: dict[str, Any]) -> Any:
    """Canonicalize equivalent representations without repairing factual errors."""

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
