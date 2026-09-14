# API

Base URL:

```text
http://127.0.0.1:4812
```

Authenticated routes require:

```text
X-Local-AI-Key: <gateway key>
```

Applications should also send a stable project identifier:

```text
X-Project-ID: itqaan
```

so operational metrics can be grouped without storing prompt content.

## Profiles

| Profile | Current mapping | Intended use |
|---|---|---|
| `fast` | Gemma 4 12B | Experimental fast candidate |
| `balanced` | Gemma 4 12B | Historical benchmark compatibility |
| `default` | GPT-OSS 20B / low | Normal application work |
| `deep` | GPT-OSS 20B / high | Difficult tasks that justify extra reasoning |

Generation endpoints accept an optional explicit `reasoning` override: `low`, `medium`, or `high`. An override changes reasoning effort without requiring callers to know the raw model ID.

## `GET /health`

Unauthenticated process health check. It does not contact LM Studio or load a model.

```json
{"status":"ok"}
```

## `GET /v1/status`

Returns LM Studio availability, loaded models when reported by LM Studio, and the configured public profiles.

## `GET /v1/models`

Returns public profile mappings. Normal applications should use profile names rather than raw model IDs.

## `POST /v1/generate`

Free-form generation.

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

With the current production configuration, `quality: "default"` and `reasoning: null` resolves to GPT-OSS 20B with low reasoning.

Response fields include the visible text, resolved model/profile/reasoning, token counts, latency metrics when available, and an opaque `request_id`.

## `POST /v1/extract`

Schema-constrained extraction with local validation and bounded repair retries.

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

The extraction API uses `format: "time"` as a convenience for a **local 24-hour `HH:MM` clock value**. This is intentionally narrower than standard JSON Schema's RFC 3339 `time`, which can contain seconds and timezone information.

Before generation, the gateway creates a model-facing copy of the schema, replaces a string `format: "time"` with an explicit `HH:MM` pattern, strips private `x-*` annotations, and adds matching natural-language representation hints to the prompt.

The original caller schema remains authoritative for gateway-side normalization and validation.

A local value such as `23:59:00` can canonicalize to `23:59` only when seconds are exactly zero and no timezone/offset is present. A value such as `18:59:00Z` is deliberately **not** rewritten because removing the suffix could hide a timezone-conversion error.

Example response:

```json
{
  "data": {
    "course": "MAT186",
    "due_date": "2026-09-18",
    "due_time": "23:59"
  },
  "model": "openai/gpt-oss-20b",
  "profile": "default",
  "reasoning": "low",
  "attempts": 1,
  "validated": true,
  "request_id": "..."
}
```

## `POST /v1/classify`

Closed-label classification implemented through enum-constrained structured output.

Request:

```json
{
  "text": "Homework 4. Due Sunday at 11:59 PM.",
  "labels": ["assignment", "exam", "announcement", "irrelevant"],
  "quality": "default",
  "max_output_tokens": 512
}
```

The gateway constructs a JSON schema whose `label` property is an enum of the supplied labels, so a successful response cannot invent another label.

The gateway does **not** invent definitions for ambiguous labels. If labels can overlap (for example, whether a message is an announcement versus whether it refers to an assignment), callers should choose mutually exclusive labels or supply a system instruction that defines the classification target.

`max_output_tokens` defaults to `512`. The original 128-token ceiling was too small for a reasoning model because hidden reasoning could consume the generation budget before the tiny final JSON result was emitted.

## Structured failure diagnostics

Structured-generation failures retain the final validation errors and, when available, LM Studio's `finish_reason`, output-token count, and reasoning-token count. A length-limited empty response is therefore reported explicitly rather than appearing as a generic JSON parse failure.

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

Current codes include:

- `AUTH_FAILED`
- `INVALID_REQUEST`
- `LMSTUDIO_UNAVAILABLE`
- `OUTPUT_INVALID`

Provider and validation failures are also recorded as operational metrics without storing prompt/response content.
