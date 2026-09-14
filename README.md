# Local AI Gateway

A localhost-only AI service for personal projects. Applications call one stable API while the gateway owns model selection, reasoning effort, structured-output validation, retries, and operational metrics.

## Current production profiles

```text
Your apps / taheem_ai SDK
        |
        v
Local AI Gateway :4812
        |
        v
LM Studio :1234
        |
        +-- fast      -> Gemma 4 12B (experimental candidate)
        +-- balanced  -> Gemma 4 12B (historical compatibility profile)
        +-- default   -> GPT-OSS 20B / low reasoning
        +-- deep      -> GPT-OSS 20B / high reasoning
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

If `.venv` already exists, just activate it and rerun `pip install -r requirements.txt` after dependency changes.

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

GitHub Actions runs the same checks.

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

## 8. Python SDK

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

`AsyncAI` provides the same generation, extraction, and classification methods for async applications.

## 9. Metrics

Requests are recorded in `data/gateway.db`. Prompt and response content are not stored.

```powershell
python scripts\gateway_stats.py --days 30
```

## 10. Benchmarks

The committed low/medium/high reasoning experiment is historical evidence and is never rewritten in place. Current benchmark runs use benchmark v3, which clarifies ambiguities found during that experiment.

Example:

```powershell
python benchmarks\run_benchmarks.py `
    --quality default `
    --reasoning low `
    --max-output-tokens 4096 `
    --name gptoss-low-v3
```

See [`benchmarks/README.md`](benchmarks/README.md) for versioning, regrading, run comparison, and manual-review policy.

## Security rules

- LM Studio stays on `127.0.0.1:1234`.
- The gateway stays on `127.0.0.1:4812`.
- Never port-forward either service directly to the public internet.
- Keep `.env` private.
- Prompt content is not logged by default.
- Cloud fallback is not implemented in this milestone, so a local failure cannot silently create API charges.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system boundaries and request path
- [`docs/api.md`](docs/api.md) — HTTP endpoints and contracts
- [`docs/current-models.md`](docs/current-models.md) — current routing decision and benchmark basis
- [`docs/structured-output.md`](docs/structured-output.md) — structured generation/validation rules
- [`docs/benchmarking.md`](docs/benchmarking.md) — benchmark history and methodology
- [`docs/development.md`](docs/development.md) — coding conventions and release checks
