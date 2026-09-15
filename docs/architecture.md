# Architecture

## Purpose

The gateway is a stable abstraction between personal applications and local AI runtimes. Applications request capabilities such as generation, extraction, classification, embeddings, semantic retrieval, grounded answering, or tool-call planning. They use public capabilities/profiles rather than raw provider model IDs.

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
   +-- stateless tool-call protocol validation
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

Application tool handlers deliberately remain **outside** the gateway process. The gateway may validate a model-requested call, but the application decides whether executable code runs.

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

`format: "time"` is intentionally narrower than standard RFC 3339 time inside this API: it means a local 24-hour `HH:MM` clock value.

## Classification

Classification is implemented as structured generation with a caller-supplied enum. This guarantees that successful responses contain exactly one allowed label, while label meaning remains the caller's responsibility.

## Embeddings

`/v1/embeddings` calls LM Studio's OpenAI-compatible embedding endpoint through a provider adapter. The gateway owns the configured embedding model key, optional model-specific prefixes, input-size limits, batching, and vector-count/dimension validation.

Applications may request `raw`, `query`, or `document` embedding purpose without knowing the concrete model.

## RAG indexing and persistence

The first RAG store is deliberately SQLite-based. It is optimized for deployment simplicity and inspectability rather than large-scale approximate nearest-neighbour search.

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

`/v1/rag/search` embeds the query in the same vector space, optionally filters exact scalar metadata, and ranks compatible chunks by cosine similarity. The brute-force implementation is intentional for the expected initial personal collection sizes.

## RAG grounded answering

`/v1/rag/answer` composes retrieval with structured generation:

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

Retrieved text is explicitly marked as **untrusted data**. Commands or prompt fragments inside indexed content do not grant permissions.

## Tool-calling abstraction

Stage 2 intentionally separates **planning/validation** from **execution authority**.

The low-level flow is:

```text
Application
   |
   | messages + JSON-Schema tool definitions
   v
POST /v1/tools/turn
   |
   +-- validate definitions/history/limits
   +-- route generation profile
   v
LM Studio /v1/chat/completions
   |
   | text OR provider tool_calls
   v
Gateway normalization
   |
   +-- reject unknown tool names
   +-- parse arguments
   +-- validate arguments against advertised schema
   +-- normalize call IDs + risk metadata
   v
Application
   |
   +-- authorize locally
   +-- execute trusted handler or refuse
   +-- append matching tool result
   v
POST /v1/tools/turn (tool_choice=none for synthesis)
```

LM Studio's native `/api/v1/chat` endpoint is not used for custom application tools because custom tool definitions belong on the OpenAI-compatible tool-calling surface. Provider-specific objects are translated inside `app/lmstudio.py`; applications see the gateway's stable call shape.

### Execution authority

The gateway **never executes arbitrary caller application code**. This is deliberate:

- accepting serialized Python/shell commands would create a remote-code-execution surface;
- hard-coding every application tool in the gateway would couple unrelated projects to infrastructure releases;
- LM Studio integrations/MCPs are useful capabilities, but they are not the application's authorization boundary.

The Python SDK therefore owns `ToolRegistry`. A registry entry contains a trusted local callable, JSON Schema, description, and risk label. Registration is the local capability grant.

The SDK validates arguments again immediately before execution. This duplication is intentional defense in depth; local execution does not depend solely on a remote response having been validated correctly.

### Risk policy

Tools are classified as `read`, `write`, or `destructive`.

`run_tools_once()` defaults to `read` only. The complete requested batch is preflighted before the first handler runs, so an unauthorized later call cannot cause earlier handlers to execute. Applications must explicitly opt into write/destructive risks and remain responsible for domain-specific confirmation/transaction semantics.

### Bounded orchestration

`run_tools_once()` permits exactly one execution round:

```text
model turn (auto)
   -> no calls: return text
   -> calls: preflight -> execute -> append results
             -> model turn with tools disabled
             -> return text
```

It does not recursively call more tools after seeing results. Multi-round planning, loop detection, cancellation, budgets, approvals, and long-running state belong to Stage 7 (bounded agents).

### Tool-result prompt injection

Tool results are untrusted external data. Mandatory gateway instructions tell the model that tool-output content is evidence/data, not policy or authorization. The stronger security boundary remains architectural: the model can request a call but cannot directly invoke application handlers.

## Metrics and data boundaries

Operational metadata is stored in `data/gateway.db`. Records include project ID, endpoint, profile/capability label, model, reasoning level, token counts, latency, attempts, success/failure, and error code.

Prompt/response contents, tool definitions, tool arguments, conversation text, and tool results are not stored by the metrics layer.

RAG is different: `data/rag.db` intentionally contains indexed source text, metadata, and vectors because retrieval cannot work without them. It must therefore be treated as private user data and remains git-ignored.

## Failure handling

Gateway-owned failures use stable error codes including `AUTH_FAILED`, `INVALID_REQUEST`, `LMSTUDIO_UNAVAILABLE`, `OUTPUT_INVALID`, `TOOL_SCHEMA_INVALID`, `TOOL_HISTORY_INVALID`, `TOOL_CALL_INVALID`, `TOOL_CALL_REQUIRED`, `EMBEDDING_DIMENSION_CHANGED`, and `RAG_INDEX_INCOMPATIBLE`.

## Security boundary

Both network services bind only to loopback:

- LM Studio: `127.0.0.1:1234`
- Gateway: `127.0.0.1:4812`

Remote access, if added later, must use a private authenticated network rather than public port forwarding.

## Benchmarks versus production safeguards

Generation, RAG retrieval, and tool calling have separate fixed benchmark suites. Tool-calling benchmarks measure selection/arguments/synthesis without executing real side effects. Real handler execution is separately covered by SDK tests and live smoke tests.

Historical benchmark artifacts are immutable. New benchmark results are saved in new directories.

## Future layers

The next roadmap stage is streaming, but it does not begin automatically. Later stages can add a local playground, model lifecycle/smarter routing, vision, bounded agents, caching/queueing/concurrency, private remote access, and explicit optional cloud fallback without changing the core application contract.
