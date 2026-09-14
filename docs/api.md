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

`max_output_tokens` defaults to `512`. The original 128-token ceiling was too small for a reasoning model because hidden reasoning could consume the generation budget before the tiny final JSON result was emitted.

## `POST /v1/embeddings`

Generate dense vectors independently of RAG storage.

Request:

```json
{
  "input": [
    "turnbuckles adjust cable tension",
    "inverse functions"
  ],
  "purpose": "raw"
}
```

`purpose` is one of:

- `raw` — no task prefix; useful for general embedding consumers;
- `query` — applies `EMBEDDING_QUERY_PREFIX` before embedding;
- `document` — applies `EMBEDDING_DOCUMENT_PREFIX` before embedding.

BGE-M3 uses blank prefixes in the default configuration. These prefix settings exist so a different embedding family can be used without leaking model-specific prompt conventions into applications.

Example response:

```json
{
  "embeddings": [[0.0123, -0.044, 0.0081]],
  "model": "text-embedding-bge-m3-embeddings",
  "dimensions": 1024,
  "input_tokens": 7,
  "request_id": "..."
}
```

The concrete dimension is whatever the configured LM Studio embedding model returns; clients should not hard-code it.

## `POST /v1/rag/index`

Chunk and index one or more logical documents into a named persistent collection.

Request:

```json
{
  "collection": "university",
  "documents": [
    {
      "id": "civ100-turnbuckles",
      "source": "CIV100 notes",
      "text": "A turnbuckle is an adjustable connector used to change tension...",
      "metadata": {
        "course": "CIV100",
        "week": 2
      }
    }
  ],
  "chunk_size_chars": 1200,
  "chunk_overlap_chars": 180
}
```

`id` is optional. If present, reindexing the same `(collection, id)` atomically replaces its old chunks. If omitted, a deterministic ID is derived from source + text.

Metadata values are intentionally scalar (`string`, `number`, `boolean`, or `null`) in this milestone so filtering semantics remain deterministic.

Example response:

```json
{
  "collection": "university",
  "documents": 1,
  "chunks": 3,
  "embedding_model": "text-embedding-bge-m3-embeddings",
  "embedding_dimensions": 1024,
  "request_id": "..."
}
```

A collection cannot silently mix embedding models or dimensions. After changing the embedding model, delete/reindex incompatible collections.

## `POST /v1/rag/search`

Run semantic retrieval without generation.

Request:

```json
{
  "collection": "university",
  "query": "How do I adjust cable tension?",
  "top_k": 5,
  "min_score": 0.0,
  "metadata_filter": {
    "course": "CIV100"
  }
}
```

Example hit:

```json
{
  "rank": 1,
  "score": 0.812345,
  "document_id": "civ100-turnbuckles",
  "chunk_index": 0,
  "source": "CIV100 notes",
  "text": "A turnbuckle is an adjustable connector...",
  "metadata": {
    "course": "CIV100",
    "week": 2
  }
}
```

Scores are cosine similarities. There is deliberately no universal default relevance cutoff: score distributions depend on the embedding model and corpus. Tune `min_score` from measured application data.

## `POST /v1/rag/answer`

Retrieve local evidence, then answer using only those sources.

Request:

```json
{
  "collection": "university",
  "query": "What does a turnbuckle do?",
  "top_k": 5,
  "quality": "default",
  "reasoning": null,
  "max_output_tokens": 2048
}
```

The answer step uses structured generation. Retrieved chunks are assigned gateway-generated labels such as `S1`, `S2`, and `S3`; the model's citation array is constrained to an enum containing only the labels actually supplied to it. The gateway then resolves those labels back to source metadata.

Example response shape:

```json
{
  "answer": "A turnbuckle lets you adjust the tension or effective length of a cable or tie.",
  "citations": [
    {
      "label": "S1",
      "document_id": "civ100-turnbuckles",
      "chunk_index": 0,
      "source": "CIV100 notes",
      "score": 0.812345,
      "metadata": {"course": "CIV100"}
    }
  ],
  "retrieved": [],
  "model": "openai/gpt-oss-20b",
  "profile": "default",
  "reasoning": "low",
  "attempts": 1,
  "request_id": "..."
}
```

If no chunks pass retrieval, the endpoint returns an explicit insufficient-information answer and does not invoke the generation model.

Retrieved source text is treated as **untrusted data**. A dedicated system rule instructs the generation model not to follow prompts, commands, or policies embedded inside retrieved sources. This reduces prompt-injection risk but should not be treated as an authorization boundary for future tools.

## `GET /v1/rag/collections`

Return indexed collection names, document/chunk counts, and embedding signatures.

## `DELETE /v1/rag/collections/{collection}`

Delete all chunks in one collection. Returns:

```json
{"deleted_chunks": 42}
```

## `DELETE /v1/rag/collections/{collection}/documents/{document_id}`

Delete one logical document and all of its chunks.

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
- `EMBEDDING_DIMENSION_CHANGED`
- `RAG_INDEX_INCOMPATIBLE`

Provider and validation failures are recorded as operational metrics without storing prompt/response content. RAG source text is stored separately in `data/rag.db` by design and should be treated as private local application data.
