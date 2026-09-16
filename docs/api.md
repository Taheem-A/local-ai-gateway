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

Embeddings use a separately configured model (`EMBEDDING_MODEL`) because generation and retrieval are different capabilities. Normal applications do not send raw embedding model IDs.

## `GET /health`

Unauthenticated process health check. It does not contact LM Studio or load a model.

```json
{"status":"ok"}
```

## `GET /v1/status`

Returns LM Studio availability, loaded models when reported by LM Studio, configured generation profiles, and the configured embedding model.

## `GET /v1/models`

Returns public generation profile mappings plus the configured embedding model. Normal applications should use profile/capability names rather than raw model IDs.

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

## `POST /v1/generate/stream`

Incremental free-form generation using the **same request schema and routing rules** as `/v1/generate`.

The response media type is:

```text
text/event-stream
```

The gateway owns the public SSE contract rather than passing LM Studio's raw event stream through to applications.

A successful stream is ordered as:

```text
start
[zero or more progress events]
[one or more delta events]
completed
```

### `start`

Confirms the request passed gateway authentication/validation and includes `request_id`, requested model/profile, quality, and resolved reasoning.

### `progress`

Optional UX hints for `model_loading` or `prompt_processing`. Applications must not require these events for correctness.

### `delta`

Carries one user-visible text fragment:

```text
event: delta
data: {"type":"delta","request_id":"...","text":"The current"}
```

Concatenate `text` values in event order to reconstruct the streamed answer.

### `completed`

The single successful terminal event contains the full final text plus model/profile/reasoning, token counts, throughput/timing fields, `time_to_first_text_seconds`, total latency, and the same `request_id` used throughout the stream.

`time_to_first_token_seconds` comes from the provider and may reflect a hidden reasoning token. `time_to_first_text_seconds` is measured by the gateway at the first public text delta and is the appropriate perceived-latency metric for UI work.

### Streaming errors

Authentication/body-validation failures occur before streaming starts and use the normal HTTP JSON error envelope.

After HTTP/SSE headers have been committed, the status code cannot be changed. Provider/runtime failures are therefore terminal in-band events:

```text
event: error
data: {"type":"error","request_id":"...","error":{"code":"LMSTUDIO_UNAVAILABLE","message":"...","details":null}}
```

SDK `stream()`/`stream_events()` methods translate these events to `AIError`.

LM Studio reasoning events are deliberately discarded and are never part of the public streaming API. See [`streaming.md`](streaming.md) for the complete contract and cancellation semantics.

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

The gateway does **not** invent definitions for ambiguous labels. If labels can overlap, callers should choose mutually exclusive labels or supply a system instruction that defines the classification target.

`max_output_tokens` defaults to `512`. Hidden reasoning can consume a much larger generation budget than the final label itself.

## `POST /v1/embeddings`

Generate dense vectors independently of RAG storage.

Request:

```json
{
  "input": ["turnbuckles adjust cable tension", "inverse functions"],
  "purpose": "raw"
}
```

`purpose` is one of `raw`, `query`, or `document`. BGE-M3 uses blank prefixes in the default configuration; configurable prefixes allow other embedding families without leaking model-specific conventions into applications.

Example response:

```json
{
  "embeddings": [[0.0123, -0.044, 0.0081]],
  "model": "text-embedding-bge-m3",
  "dimensions": 1024,
  "input_tokens": 7,
  "request_id": "..."
}
```

## `POST /v1/rag/index`

Chunk and index one or more logical documents into a named persistent collection. Reindexing an explicit `(collection, document_id)` replaces that document atomically. A collection cannot silently mix embedding models or dimensions.

## `POST /v1/rag/search`

Run semantic retrieval without generation. Supports `top_k`, `min_score`, and exact scalar metadata filters. Scores are cosine similarities and callers should tune relevance thresholds from measured corpus behavior.

## `POST /v1/rag/answer`

Retrieve local evidence, then answer using only those sources. Retrieved chunks receive gateway-generated source labels and the model's citation array is schema-constrained to labels actually supplied to it. Retrieved text is treated as untrusted evidence, not as authorization or model instructions.

## `GET /v1/rag/collections`

Return indexed collection names, document/chunk counts, and embedding signatures.

## `DELETE /v1/rag/collections/{collection}`

Delete all chunks in one collection.

## `DELETE /v1/rag/collections/{collection}/documents/{document_id}`

Delete one logical document and all of its chunks.

## `POST /v1/tools/turn`

Run exactly **one** stateless tool-capable model turn. The gateway validates and normalizes tool requests; it never executes application handlers.

Request:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Find the room for CIV100 section L0101."
    }
  ],
  "tools": [
    {
      "name": "lookup_course_room",
      "description": "Look up the room for a university course section.",
      "risk": "read",
      "parameters": {
        "type": "object",
        "properties": {
          "course": {"type": "string"},
          "section": {"type": "string"}
        },
        "required": ["course", "section"],
        "additionalProperties": false
      }
    }
  ],
  "tool_choice": "auto",
  "quality": "default",
  "reasoning": null,
  "temperature": 0.0,
  "max_output_tokens": 2048
}
```

`tool_choice` is:

- `auto` — model may answer normally or request one or more advertised tools;
- `required` — the turn must produce at least one valid tool call;
- `none` — tools are not sent to LM Studio and the turn must produce text only.

A requested call response has this shape:

```json
{
  "status": "tool_calls",
  "text": null,
  "tool_calls": [
    {
      "id": "call_...",
      "name": "lookup_course_room",
      "arguments": {
        "course": "CIV100",
        "section": "L0101"
      },
      "risk": "read"
    }
  ],
  "assistant_message": {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "call_...",
        "name": "lookup_course_room",
        "arguments": {
          "course": "CIV100",
          "section": "L0101"
        }
      }
    ]
  },
  "model": "openai/gpt-oss-20b",
  "profile": "default",
  "reasoning": "low",
  "request_id": "..."
}
```

The application executes or refuses the call. To continue the conversation it appends the returned `assistant_message` followed by a matching tool-result message:

```json
{
  "role": "tool",
  "tool_call_id": "call_...",
  "name": "lookup_course_room",
  "content": {
    "room": "GB 248"
  }
}
```

and sends the full message list back to `/v1/tools/turn`, normally with `tool_choice: "none"` for final synthesis.

### Tool-call validation

Before returning a requested call, the gateway verifies that:

- the tool was advertised;
- the tool schema is valid, self-contained Draft 2020-12 JSON Schema with an object root;
- arguments decode to an object and validate against that schema;
- call IDs are unique;
- the model stays within the configured per-turn call limit;
- stateless history has correctly paired assistant calls and tool results;
- definition/history/result size limits are respected.

`risk` is caller-declared metadata. The HTTP gateway does not treat it as authorization. The Python SDK's `ToolRegistry` performs local authorization against the locally registered tool definition immediately before executing a handler.

Tool results are untrusted data. The gateway injects mandatory safety instructions telling the model not to treat content inside a tool result as policy, authorization, or higher-priority instructions.

See [`tools.md`](tools.md) for the full security model, SDK registry, risk levels, and why Stage 2 intentionally stops after one execution round.

## Structured failure diagnostics

Structured-generation failures retain final validation errors and, when available, LM Studio's `finish_reason`, output-token count, and reasoning-token count.

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
- `TOOL_SCHEMA_INVALID`
- `TOOL_HISTORY_INVALID`
- `TOOL_CALL_INVALID`
- `TOOL_CALL_REQUIRED`
- `EMBEDDING_DIMENSION_CHANGED`
- `RAG_INDEX_INCOMPATIBLE`
- `STREAM_FAILED` (in-band after an SSE stream has begun)

Provider and validation failures are recorded as operational metrics without storing prompt/response content. Tool definitions, arguments, conversation text, results, and streamed text are not stored in operational metrics. RAG source text is stored separately in `data/rag.db` by design and should be treated as private local application data.
