# API

Base URL:

```text
http://127.0.0.1:4812
```

Authenticated routes require:

```text
X-Local-AI-Key: <gateway key>
```

Applications should also send:

```text
X-Project-ID: itqaan
```

so operational metrics can be grouped by project.

## Profiles

- `fast`: current Gemma fast candidate.
- `balanced`: historical Gemma benchmark profile; preserved for reproducibility.
- `default`: GPT-OSS 20B / medium reasoning; recommended for new application code.
- `deep`: GPT-OSS 20B / medium reasoning until the reasoning-level benchmark is finished.

All generation endpoints also accept an optional explicit `reasoning` override: `low`, `medium`, or `high`.

## `GET /health`

Unauthenticated lightweight process health check. Does not invoke a model.

```json
{"status":"ok"}
```

## `GET /v1/status`

Returns LM Studio availability, loaded models when reported by LM Studio, and configured profiles.

## `GET /v1/models`

Returns public profile mappings. Normal applications should use profile names rather than raw model IDs.

## `POST /v1/generate`

Request:

```json
{
  "prompt": "Explain dependency injection.",
  "system": null,
  "quality": "default",
  "reasoning": null,
  "temperature": 0.2,
  "max_output_tokens": 2048
}
```

## `POST /v1/extract`

Request:

```json
{
  "prompt": "MAT186 Problem Set 2 is due September 18, 2026 at 11:59 PM.",
  "quality": "default",
  "schema": {
    "type": "object",
    "properties": {
      "course": {"type": "string", "x-normalize": "upper"},
      "due_date": {"type": "string", "format": "date"},
      "due_time": {"type": "string", "format": "time"}
    },
    "required": ["course", "due_date", "due_time"],
    "additionalProperties": false
  },
  "max_attempts": 2
}
```

### Canonical local times

The gateway's extraction API uses `format: "time"` as a convenience for a **local 24-hour `HH:MM` clock value**. This is intentionally narrower than standard JSON Schema's RFC 3339 `time` format, which can contain seconds and a timezone suffix.

Before the schema is sent to LM Studio, the gateway makes a model-facing copy and translates a string field with `format: "time"` to an exact `HH:MM` regular-expression constraint. For example, a source value of `11:59 PM` must be returned as `23:59`; the model should not convert it to UTC or append `:00Z`.

The original caller schema remains authoritative for gateway-side normalization and validation. Private gateway annotations such as `x-normalize` are stripped from the model-facing copy.

Response:

```json
{
  "data": {
    "course": "MAT186",
    "due_date": "2026-09-18",
    "due_time": "23:59"
  },
  "model": "openai/gpt-oss-20b",
  "profile": "default",
  "reasoning": "medium",
  "attempts": 1,
  "validated": true,
  "request_id": "..."
}
```

## `POST /v1/classify`

Request:

```json
{
  "text": "Homework 4 is due Sunday.",
  "labels": ["assignment", "exam", "announcement", "irrelevant"],
  "quality": "default",
  "max_output_tokens": 512
}
```

The gateway internally constructs a JSON schema whose label property is an enum, so the model cannot legally return a label outside the supplied set.

`max_output_tokens` defaults to `512` for classification. The previous `128`-token hard cap was unsafe for reasoning models such as GPT-OSS: hidden reasoning can consume the generation budget before the model emits the tiny final JSON object. Values below `128` are rejected for this endpoint.

Structured-generation failures now preserve LM Studio's `finish_reason` plus token diagnostics when available. A length-limited empty response is reported explicitly instead of looking like a generic JSON parse failure.

## Errors

Gateway-owned errors use a stable envelope:

```json
{
  "error": {
    "code": "OUTPUT_INVALID",
    "message": "The model failed structured-output validation after 2 attempt(s).",
    "details": {}
  }
}
```

Current gateway codes include:

- `AUTH_FAILED`
- `INVALID_REQUEST`
- `LMSTUDIO_UNAVAILABLE`
- `OUTPUT_INVALID`

More stable codes can be added as later tool/RAG/agent layers are implemented.
