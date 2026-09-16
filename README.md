# Local AI Gateway

A localhost-only AI service for personal projects. Applications call one stable API while the gateway owns model selection, reasoning effort, streaming, embeddings, retrieval-augmented generation (RAG), structured-output validation, safe tool-call planning, retries, and operational metrics.

## Current production profiles

```text
Your apps / taheem_ai SDK
        |
        v
Local AI Gateway :4812
        |
        +-- generation ----------------------+
        |   +-- JSON response                |
        |   +-- normalized SSE stream        v
        |                           LM Studio :1234
        |                                    |
        |   +-- fast      -> Gemma 4 12B (experimental candidate)
        |   +-- balanced  -> Gemma 4 12B (historical compatibility profile)
        |   +-- default   -> GPT-OSS 20B / low reasoning
        |   +-- deep      -> GPT-OSS 20B / high reasoning
        |
        +-- embeddings/RAG -> BGE-M3 -> data/rag.db
        |
        +-- tool planning -> GPT-OSS -> validated call request
                                      -> application-owned handler
```

New applications should normally use `default`. Use `deep` when a task justifies substantially more reasoning time. `medium` reasoning remains available as an explicit override. `balanced` intentionally preserves the original Gemma benchmark mapping so old experiments stay reproducible.

The default/deep decision comes from the frozen September 2026 low/medium/high GPT-OSS benchmark. See [`benchmarks/history/2026-09-13-gptoss-reasoning/`](benchmarks/history/2026-09-13-gptoss-reasoning/).

## 1. Install dependencies

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `.venv` already exists, activate it and rerun `pip install -r requirements.txt` after dependency changes.

## 2. Configure `.env`

```powershell
Copy-Item .env.example .env
```

Insert your real LM Studio token and gateway key. Never commit `.env`.

The production reasoning values should be:

```dotenv
REASONING_DEFAULT=low
REASONING_DEEP=high
```

RAG additionally needs an embedding model. The preferred default is BGE-M3:

```dotenv
EMBEDDING_MODEL=text-embedding-bge-m3
EMBEDDING_QUERY_PREFIX=
EMBEDDING_DOCUMENT_PREFIX=
```

The exact LM Studio model key can vary by downloaded revision, so confirm it locally with `lms ls --embedding` and override `EMBEDDING_MODEL` when necessary. Existing RAG collections must be reindexed after changing embedding model or dimension.

## 3. Start the local services

Start LM Studio on loopback only:

```powershell
lms server start --port 1234
```

Start the gateway:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 4812
```

or:

```powershell
scripts\start_gateway.cmd
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:4812/health
```

Expected:

```json
{"status":"ok"}
```

## 4. Quality checks

Before committing Python changes:

```powershell
ruff check .
python -m compileall -q app benchmarks clients/python/taheem_ai scripts tests work
pytest -q
```

GitHub Actions runs the same checks. CI uses fake deterministic embeddings and mocked tool/provider responses, so it does not require LM Studio or GPU access.

## 5. Free-form generation

```powershell
$headers = @{
    "X-Local-AI-Key" = $env:GATEWAY_API_KEY
    "X-Project-ID" = "test"
    "Content-Type" = "application/json"
}

$body = @{
    prompt = "Explain dependency injection in three paragraphs."
    quality = "default"
    max_output_tokens = 1024
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:4812/v1/generate" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

`default` resolves to GPT-OSS 20B with low reasoning unless the request explicitly supplies `reasoning`.

## 6. Structured extraction

`/v1/extract` combines LM Studio JSON-schema constrained generation with gateway-side normalization, Draft 2020-12 validation, and bounded repair retries.

For this gateway, `format = "time"` means an exact local `HH:MM` clock value. The gateway translates that convenience contract to a model-facing pattern and deliberately refuses to hide timezone conversions.

See [`docs/structured-output.md`](docs/structured-output.md) for the complete contract.

## 7. Classification

`/v1/classify` performs enum-constrained closed-label classification. The caller owns the label semantics; overlapping labels should be clarified through mutually exclusive names or a system instruction.

## 8. Embeddings and RAG

Raw embeddings are available through `/v1/embeddings`. Persistent RAG adds `/v1/rag/index`, `/v1/rag/search`, `/v1/rag/answer`, collection inspection, document deletion, and local file/PDF ingestion.

```powershell
python scripts\rag_ingest.py university C:\path\to\notes --recursive --project university
```

Retrieved text is explicitly treated as untrusted evidence rather than model instructions. See [`docs/rag.md`](docs/rag.md) for architecture, persistence, prompt-injection handling, reindex rules, and scaling strategy.

## 9. Tool calling

Stage 2 provides a provider-independent tool-call abstraction without making the gateway an arbitrary-code execution service.

The low-level endpoint:

```text
POST /v1/tools/turn
```

runs exactly one model turn. The caller supplies self-contained JSON-Schema tool definitions and conversation history; the gateway validates schemas/history and returns either normal text or validated tool-call requests.

The gateway **never executes caller application code**. Execution authority stays in the application. The Python SDK provides `ToolRegistry` for trusted local handlers:

```python
from taheem_ai import AI, ToolRegistry


def lookup_course_room(course: str, section: str) -> dict:
    return {"course": course, "section": section, "room": "GB 248"}


registry = ToolRegistry().register(
    name="lookup_course_room",
    description="Look up the room for a university course section.",
    parameters={
        "type": "object",
        "properties": {
            "course": {"type": "string"},
            "section": {"type": "string"},
        },
        "required": ["course", "section"],
        "additionalProperties": False,
    },
    handler=lookup_course_room,
    risk="read",
)

ai = AI(project="university")
result = ai.run_tools_once("Where is CIV100 section L0101?", registry)
print(result.text)
```

`run_tools_once()` defaults to `read` tools only, preflights the entire requested batch before executing anything, performs at most one execution round, then forces text-only synthesis. `write` and `destructive` tools require explicit opt-in. Recursive multi-step autonomy is intentionally deferred to Stage 7.

Tool outputs are treated as untrusted data and cannot grant permission or add tools. See [`docs/tools.md`](docs/tools.md) for the complete security and execution model.

## 10. Streaming

`POST /v1/generate/stream` accepts the same generation request as `/v1/generate`, but returns normalized Server-Sent Events so applications can render text as it is generated.

The public event types are:

```text
start
progress     # optional model-load/prompt-processing status
delta        # user-visible text only
completed    # final text + token/timing metadata
error        # terminal in-band failure after streaming begins
```

LM Studio's hidden reasoning events are never forwarded. The gateway also measures `time_to_first_text_seconds` separately from the provider's first-token timing, because hidden reasoning may happen before the first character a user can actually see.

Python SDK v0.4 text streaming is intentionally tiny:

```python
from taheem_ai import AI

ai = AI(project="demo")
for text in ai.stream("Explain DNS in five sentences."):
    print(text, end="", flush=True)
```

Use `stream_events()` when the application also needs progress or final token/timing metadata. Matching async iterators are available on `AsyncAI`.

See [`docs/streaming.md`](docs/streaming.md) for the event contract, cancellation behavior, error semantics, and scope boundary.

## 11. Python SDK

Install the local client in editable mode:

```powershell
pip install -e .\clients\python
```

Set `LOCAL_AI_GATEWAY_KEY`, then:

```python
from taheem_ai import AI

ai = AI(project="itqaan")
print(ai.ask("Explain this error."))
```

The SDK also provides streaming, typed extraction, classification, embeddings, RAG indexing/search/answers, low-level `tool_turn()`, bounded `run_tools_once()`, and matching async APIs.

## 12. Metrics and benchmarks

Operational requests are recorded in `data/gateway.db`; prompt, response, tool-definition, tool-argument, tool-result, and streamed text content are not stored there. RAG source text and vectors live separately in `data/rag.db` and are private application data by design.

```powershell
python scripts\gateway_stats.py --days 30
```

Generation, retrieval, tool calling, and streaming have separate benchmark suites. Streaming can be tested with:

```powershell
python benchmarks\run_stream_benchmarks.py --quality default --name gptoss-streaming-v1
```

See [`benchmarks/README.md`](benchmarks/README.md).

## Security rules

- LM Studio stays on `127.0.0.1:1234`.
- The gateway stays on `127.0.0.1:4812`.
- Never port-forward either service directly to the public internet.
- Keep `.env`, `data/gateway.db`, and `data/rag.db` private.
- Prompt/tool/stream content is not logged by operational metrics by default.
- Hidden reasoning is not exposed by the streaming API.
- Retrieved RAG content and tool results are untrusted data, never authorization.
- A model-requested tool call is only a request; application policy decides whether code executes.
- Cloud fallback is not implemented, so a local failure cannot silently create API charges.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system boundaries and request path
- [`docs/api.md`](docs/api.md) — HTTP endpoints and contracts
- [`docs/current-models.md`](docs/current-models.md) — current routing decision and benchmark basis
- [`docs/structured-output.md`](docs/structured-output.md) — structured generation/validation rules
- [`docs/rag.md`](docs/rag.md) — embeddings, retrieval, indexing, citations, and RAG security
- [`docs/tools.md`](docs/tools.md) — tool protocol, local registry, risk policy, and security boundaries
- [`docs/streaming.md`](docs/streaming.md) — SSE events, reasoning suppression, cancellation, and SDK usage
- [`docs/benchmarking.md`](docs/benchmarking.md) — benchmark history and methodology
- [`docs/development.md`](docs/development.md) — coding conventions and release checks
