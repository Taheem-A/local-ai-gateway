from __future__ import annotations

from copy import deepcopy
from typing import Any


LOCAL_TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
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
