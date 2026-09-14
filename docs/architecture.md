# Architecture

## Purpose

The gateway is a stable abstraction between personal applications and local AI runtimes. Applications request capabilities such as generation, extraction, classification, embeddings, semantic retrieval, or grounded answering. They use public capabilities/profiles rather than raw provider model IDs.

## Request path

```text
Application
   |
   v
Python SDK or HTTP
   |
   v
FastAPI gateway (:4812)
   |
   +-- API-key authentication
   +-- generation profile + reasoning routing
   +-- structured-output validation/retries
   +-- embedding capability routing
   +-- deterministic chunking + RAG retrieval
   +-- non-content operational metrics
   |
   +-------------------------+
   |                         |
   v                         v
LM Studio (:1234)         SQLite
   |                      +-- data/gateway.db (metrics only)
   |                      +-- data/rag.db (RAG source text + vectors)
   v
Local generation and embedding models
```

## Generation profiles

- `fast`: current experimental Gemma 4 12B mapping. It is not yet the proven final fast-tier winner.
- `balanced`: historical Gemma benchmark profile preserved only for reproducibility.
- `default`: GPT-OSS 20B with **low** reasoning. This is the normal application profile.
- `deep`: GPT-OSS 20B with **high** reasoning. This is reserved for tasks that justify substantially more latency and reasoning tokens.

The low/high decision comes from the frozen September 2026 reasoning benchmark. Medium reasoning remains available as an explicit per-request override rather than occupying a production profile.

Embedding is a separate capability rather than another quality profile. `EMBEDDING_MODEL` selects the local embedding backend (BGE-M3 by default) because retrieval model choice should not alter application code or generation routing.

## Free-form generation

`/v1/generate` resolves the public profile, calls LM Studio's native local chat endpoint, and returns only `message` output items. Reasoning and tool items are excluded from the visible answer but reasoning-token counts are retained when LM Studio reports them.

## Structured output

`/v1/extract` and `/v1/classify` use a layered trust boundary:

1. prepare a model-facing JSON Schema;
2. use LM Studio constrained generation;
3. parse the returned JSON;
4. conservatively normalize equivalent representations;
5. validate locally with Draft 2020-12 JSON Schema;
6. retry a bounded number of times with exact validation errors if necessary.

The caller's schema remains authoritative for local validation. The gateway never changes a factual value merely because another value would make validation pass.

`format: "time"` is intentionally narrower than standard RFC 3339 time inside this API: it means a local 24-hour `HH:MM` clock value. The model-facing schema and prompt are prepared accordingly so timezone conversions cannot be silently hidden.

## Classification

Classification is implemented as structured generation with a caller-supplied enum. This guarantees that successful responses contain exactly one allowed label, while label meaning remains the caller's responsibility. Production callers should provide mutually exclusive labels or a system instruction that defines them.

## Embeddings

`/v1/embeddings` calls LM Studio's OpenAI-compatible embedding endpoint through a provider adapter. The gateway owns:

- the configured embedding model key;
- optional model-specific query/document prefixes;
- input-size limits;
- batching;
- vector-count and dimension validation.

Applications may request `raw`, `query`, or `document` embedding purpose without knowing the embedding model. The purpose only controls configured task-prefix behavior; it does not expose provider-specific prompt strings.

## RAG indexing and persistence

The first RAG store is deliberately SQLite-based. It is optimized for deployment simplicity and inspectability rather than large-scale approximate nearest-neighbour search.

Ingestion follows this path:

```text
Document text
   |
   v
Deterministic chunker
   |
   v
Embedding model
   |
   v
Unit-normalize vectors
   |
   v
SQLite rag_chunks table
```

The store persists source text, provenance, scalar metadata, content hashes, the embedding-model signature, and normalized float32 vectors. Reindexing an explicit document ID atomically replaces that document's old chunks.

A collection must have one embedding model and dimension. If configuration changes, the gateway returns `RAG_INDEX_INCOMPATIBLE` instead of mixing vector spaces.

## RAG retrieval

`/v1/rag/search` embeds the query in the same vector space, optionally filters exact scalar metadata, and ranks compatible chunks by cosine similarity. Because stored and query vectors are normalized, similarity reduces to a dot product.

The brute-force implementation is intentional for the expected initial personal collection sizes. The public service boundary permits a future ANN store without changing the HTTP/SDK contract.

## RAG grounded answering

`/v1/rag/answer` composes retrieval with the existing structured-generation pipeline:

```text
Question
   |
   v
Dense retrieval
   |
   v
Bounded retrieved context
   |
   +-- S1, S2, ... gateway source labels
   v
GPT-OSS generation
   |
   +-- schema: answer + citations enum[S1, S2, ...]
   v
Gateway resolves labels to document/chunk provenance
```

The model cannot successfully return an unknown citation label because citations are schema-constrained to the retrieved source IDs.

Retrieved text is explicitly marked as **untrusted data** in the system instructions. Commands, prompt fragments, and policies inside documents are evidence text, not executable instructions. This is an important prompt-injection mitigation, but it is not an authorization mechanism; the later tool-calling milestone must maintain its own permission boundary.

## Metrics and data boundaries

Operational metadata is stored in `data/gateway.db`. Records include project ID, endpoint, profile/capability label, model, reasoning level, token counts, latency, attempts, success/failure, and error code.

Prompt and response contents are intentionally not stored by the metrics layer.

RAG is different: `data/rag.db` intentionally contains indexed source text, metadata, and vectors because retrieval cannot work without them. It must therefore be treated as private user data and remains git-ignored.

## Failure handling

Gateway-owned failures use stable error codes such as `AUTH_FAILED`, `INVALID_REQUEST`, `LMSTUDIO_UNAVAILABLE`, `OUTPUT_INVALID`, `EMBEDDING_DIMENSION_CHANGED`, and `RAG_INDEX_INCOMPATIBLE`. Provider failures are recorded in the metrics database before they are translated to gateway errors.

## Security boundary

Both network services bind only to loopback:

- LM Studio: `127.0.0.1:1234`
- Gateway: `127.0.0.1:4812`

Remote access, if added later, must use a private authenticated network rather than public port forwarding.

## Benchmarks versus production safeguards

Generation benchmark runs deliberately call `/v1/generate` so raw model formatting, instruction following, and reasoning behavior remain measurable. Production structured endpoints add schema constraints, normalization, and repair retries. A raw benchmark format score therefore should not be interpreted as the production structured-output success rate.

RAG has a separate fixed multilingual retrieval benchmark. It measures retrieval ranking and latency independently of answer generation, making it possible to evaluate embedding-model/index changes without conflating them with GPT-OSS quality.

Historical benchmark artifacts are immutable. New benchmark results are saved in new directories.

## Future layers

The next milestone is the tool-calling abstraction, but it does not begin automatically. Later stages can add streaming, a local playground, model lifecycle/smarter routing, vision, bounded agents, caching/queueing/concurrency, private remote access, and explicit optional cloud fallback without changing the core application contract.
