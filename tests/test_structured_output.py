import pytest

from app.structured.normalization import normalize_instance
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
