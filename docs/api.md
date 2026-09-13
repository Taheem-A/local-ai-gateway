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

`quality` accepts:

```text
fast
balanced
(default alias compatibility)
default
deep
```

`reasoning` is optional and accepts `low`, `medium`, or `high`. When omitted, the selected profile's configured reasoning effort is used.

## `POST /v1/extract`

Request:

```json
{
  "prompt": "MAT186 Problem Set 2 is due September 18, 2026.",
  "quality": "default",
  "schema": {
    "type": "object",
    "properties": {
      "course": {"type": "string", "x-normalize": "upper"},
      "due_date": {"type": "string", "format": "date"}
    },
    "required": ["course", "due_date"],
    "additionalProperties": false
  },
  "max_attempts": 2
}
```

Response:

```json
{
  "data": {
    "course": "MAT186",
    "due_date": "2026-09-18"
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
  "quality": "default"
}
```

The gateway internally constructs a JSON schema whose label property is an enum, so the model cannot legally return a label outside the supplied set.

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
