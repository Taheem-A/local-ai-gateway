# Local AI Gateway

A localhost-only AI service for personal projects. Applications call one stable API while the gateway owns model selection, reasoning effort, embeddings, retrieval-augmented generation (RAG), structured-output validation, retries, and operational metrics.

## Current production profiles

```text
Your apps / taheem_ai SDK
        |
        v
Local AI Gateway :4812
        |
        +-- generation ----------------------+
        |                                    v
        |                           LM Studio :1234
        |                                    |
        |   +-- fast      -> Gemma 4 12B (experimental candidate)
        |   +-- balanced  -> Gemma 4 12B (historical compatibility profile)
        |   +-- default   -> GPT-OSS 20B / low reasoning
        |   +-- deep      -> GPT-OSS 20B / high reasoning
        |
        +-- embeddings/RAG -> BGE-M3 -> data/rag.db
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
EMBEDDING_MODEL=text-embedding-bge-m3-embeddings
EMBEDDING_QUERY_PREFIX=
EMBEDDING_DOCUMENT_PREFIX=
```

The exact LM Studio model key can vary by downloaded revision, so confirm it locally and override `EMBEDDING_MODEL` when necessary. Existing RAG collections must be reindexed after changing embedding model or dimension.

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

GitHub Actions runs the same checks. CI uses fake deterministic embeddings for RAG tests and therefore does not require LM Studio or GPU access.

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

```powershell
$body = @{
    prompt = "MAT186 Problem Set 2 is due September 18, 2026 at 11:59 PM."
    quality = "default"
    schema = @{
        type = "object"
        properties = @{
            course = @{ type = "string"; "x-normalize" = "upper" }
            assignment = @{ type = "string" }
            due_date = @{ type = "string"; format = "date" }
            due_time = @{ type = "string"; format = "time" }
        }
        required = @("course", "assignment", "due_date", "due_time")
        additionalProperties = $false
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
    -Uri "http://127.0.0.1:4812/v1/extract" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

For this gateway, `format = "time"` means an exact local `HH:MM` clock value. The gateway translates that convenience contract to a model-facing pattern and deliberately refuses to hide timezone conversions. A source value of `11:59 PM` therefore canonicalizes to `23:59`.

## 7. Classification

```powershell
$body = @{
    text = "Homework 4. Due Sunday at 11:59 PM."
    labels = @("assignment", "exam", "announcement", "irrelevant")
    quality = "default"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:4812/v1/classify" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

The gateway converts the supplied labels into an enum-constrained JSON schema. Classification keeps a 512-token default generation budget because hidden reasoning can consume far more tokens than the tiny visible label.

## 8. Embeddings and RAG

Raw embeddings are available independently:

```powershell
$body = @{
    input = @("turnbuckles adjust cable tension", "inverse functions")
    purpose = "raw"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:4812/v1/embeddings" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

Index text directly:

```powershell
$body = @{
    collection = "university"
    documents = @(
        @{
            id = "civ100-turnbuckles"
            source = "CIV100 notes"
            text = "A turnbuckle is an adjustable connector used to change tension..."
            metadata = @{ course = "CIV100" }
        }
    )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
    -Uri "http://127.0.0.1:4812/v1/rag/index" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

Retrieve without generation through `/v1/rag/search`, or ask a grounded question through `/v1/rag/answer`. Grounded answers use schema-constrained source labels and map citations back to the retrieved document/chunk metadata. Retrieved text is explicitly treated as untrusted data rather than model instructions.

For local files and PDFs:

```powershell
python scripts\rag_ingest.py university C:\path\to\notes --recursive --project university
```

The ingestion helper supports text/Markdown/code/JSON/YAML/CSV plus text-based PDFs. Each PDF page is kept as a separate logical source so citations retain page provenance. Scanned/image-only PDFs are not OCR'd in this milestone.

See [`docs/rag.md`](docs/rag.md) for architecture, model choice, persistence, prompt-injection handling, reindex rules, and scaling strategy.

## 9. Python SDK

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

Typed extraction:

```python
from datetime import date

from pydantic import BaseModel
from taheem_ai import AI


class Assignment(BaseModel):
    course: str
    title: str
    due_date: date


ai = AI(project="university")
assignment = ai.extract(
    "MAT186 Problem Set 2 is due September 18, 2026.",
    Assignment,
)
print(assignment)
```

RAG through SDK v0.2:

```python
from taheem_ai import AI

ai = AI(project="university")
ai.index_documents(
    "notes",
    [
        {
            "id": "mat186-ps2",
            "source": "MAT186 notes",
            "text": "Problem Set 2 is due September 18, 2026.",
            "metadata": {"course": "MAT186"},
        }
    ],
)

print(ai.search("notes", "When is Problem Set 2 due?"))
result = ai.answer_with_sources("notes", "When is Problem Set 2 due?")
print(result["answer"])
print(result["citations"])
```

`AsyncAI` provides matching generation, extraction, classification, embedding, indexing, retrieval, and grounded-answer methods for async applications.

## 10. Metrics and benchmarks

Operational requests are recorded in `data/gateway.db`; prompt and response content are not stored there. RAG source text and vectors live separately in `data/rag.db` and are private application data by design.

```powershell
python scripts\gateway_stats.py --days 30
```

The committed low/medium/high reasoning experiment remains immutable historical evidence. Current generation benchmarks use benchmark v3.

The RAG retrieval benchmark measures Recall@1/3/5, mean reciprocal rank, and retrieval latency on a fixed multilingual corpus:

```powershell
python benchmarks\run_rag_benchmarks.py --name bge-m3-rag-v1
```

See [`benchmarks/README.md`](benchmarks/README.md) and [`docs/rag.md`](docs/rag.md).

## Security rules

- LM Studio stays on `127.0.0.1:1234`.
- The gateway stays on `127.0.0.1:4812`.
- Never port-forward either service directly to the public internet.
- Keep `.env`, `data/gateway.db`, and `data/rag.db` private.
- Prompt content is not logged by operational metrics by default.
- Retrieved RAG content is untrusted evidence and must never grant instructions or permissions.
- Cloud fallback is not implemented in this milestone, so a local failure cannot silently create API charges.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system boundaries and request path
- [`docs/api.md`](docs/api.md) — HTTP endpoints and contracts
- [`docs/current-models.md`](docs/current-models.md) — current routing decision and benchmark basis
- [`docs/structured-output.md`](docs/structured-output.md) — structured generation/validation rules
- [`docs/rag.md`](docs/rag.md) — embeddings, retrieval, indexing, citations, and RAG security
- [`docs/benchmarking.md`](docs/benchmarking.md) — benchmark history and methodology
- [`docs/development.md`](docs/development.md) — coding conventions and release checks
