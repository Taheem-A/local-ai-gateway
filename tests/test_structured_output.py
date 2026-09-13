import pytest

from app.structured.normalization import normalize_instance
from app.structured.schema_prep import (
    LOCAL_TIME_PATTERN,
    add_generation_hints,
    prepare_generation_schema,
)
from app.structured.validation import check_schema, parse_json, validation_errors


def test_parse_json_accepts_plain_json():
    assert parse_json('{"ok": true}') == {"ok": True}


def test_parse_json_defensively_strips_markdown_fence():
    assert parse_json('```json\n{"ok": true}\n```') == {"ok": True}


def test_normalization_is_schema_directed():
    schema = {
        "type": "object",
        "properties": {
            "course": {"type": "string", "x-normalize": "upper"},
            "date": {"type": "string", "format": "date"},
            "time": {"type": "string", "format": "time"},
            "score": {"type": "number"},
        },
        "required": ["course", "date", "time", "score"],
        "additionalProperties": False,
    }
    value = {
        "course": " mat186 ",
        "date": "September 18, 2026",
        "time": "11:59 PM",
        "score": "82.5",
    }

    assert normalize_instance(value, schema) == {
        "course": "MAT186",
        "date": "2026-09-18",
        "time": "23:59",
        "score": 82.5,
    }


def test_generation_schema_constrains_time_to_local_hhmm():
    schema = {
        "type": "object",
        "properties": {
            "course": {"type": "string", "x-normalize": "upper"},
            "due_time": {"type": "string", "format": "time"},
        },
        "required": ["course", "due_time"],
        "additionalProperties": False,
    }

    prepared = prepare_generation_schema(schema)
    due_time = prepared["properties"]["due_time"]

    # The caller schema is never mutated.
    assert schema["properties"]["due_time"] == {"type": "string", "format": "time"}

    # LM Studio receives the exact local-time representation the API requires,
    # rather than RFC3339 `time` (which permits seconds + timezone suffixes).
    assert "format" not in due_time
    assert due_time["pattern"] == LOCAL_TIME_PATTERN
    assert "\\d" not in LOCAL_TIME_PATTERN
    assert "24-hour HH:MM" in due_time["description"]

    # Private gateway annotations are not leaked into the model-facing schema.
    assert "x-normalize" not in prepared["properties"]["course"]


def test_generation_prompt_makes_local_time_contract_visible_to_model():
    schema = {
        "type": "object",
        "properties": {
            "due_date": {"type": "string", "format": "date"},
            "due_time": {"type": "string", "format": "time"},
        },
        "required": ["due_date", "due_time"],
    }

    prompt = add_generation_hints("Extract the deadline.", schema)

    assert "due_date: use calendar date format YYYY-MM-DD" in prompt
    assert "due_time: Time in 24-hour HH:MM format" in prompt
    assert "do not convert timezones" in prompt
    assert "do not add seconds" in prompt


def test_gateway_time_validation_accepts_hhmm_and_rejects_rfc3339_time():
    schema = {
        "type": "object",
        "properties": {"due_time": {"type": "string", "format": "time"}},
        "required": ["due_time"],
    }

    assert not validation_errors({"due_time": "23:59"}, schema)
    assert validation_errors({"due_time": "18:59:00Z"}, schema)


def test_zero_second_local_time_is_safely_canonicalized():
    schema = {
        "type": "object",
        "properties": {"due_time": {"type": "string", "format": "time"}},
        "required": ["due_time"],
    }

    normalized = normalize_instance({"due_time": "23:59:00"}, schema)
    assert normalized == {"due_time": "23:59"}
    assert not validation_errors(normalized, schema)


def test_time_normalization_does_not_hide_timezone_or_nonzero_seconds():
    schema = {
        "type": "object",
        "properties": {"due_time": {"type": "string", "format": "time"}},
        "required": ["due_time"],
    }

    timezone_value = normalize_instance({"due_time": "18:59:00Z"}, schema)
    precise_value = normalize_instance({"due_time": "23:59:30"}, schema)

    assert timezone_value["due_time"] == "18:59:00Z"
    assert precise_value["due_time"] == "23:59:30"
    assert validation_errors(timezone_value, schema)
    assert validation_errors(precise_value, schema)


def test_normalization_does_not_fix_wrong_facts():
    schema = {
        "type": "object",
        "properties": {"date": {"type": "string", "format": "date"}},
        "required": ["date"],
    }
    assert normalize_instance({"date": "September 19, 2026"}, schema)["date"] == "2026-09-19"


def test_validation_rejects_missing_and_extra_fields():
    schema = {
        "type": "object",
        "properties": {"course": {"type": "string"}},
        "required": ["course"],
        "additionalProperties": False,
    }

    assert validation_errors({}, schema)
    assert validation_errors({"course": "MAT186", "extra": 1}, schema)
    assert not validation_errors({"course": "MAT186"}, schema)


def test_invalid_schema_is_rejected():
    with pytest.raises(ValueError):
        check_schema({"type": "not-a-real-json-schema-type"})
