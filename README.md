# Local AI Gateway

A localhost-only AI service for personal projects. Applications call one stable API while the gateway owns model selection, reasoning effort, structured-output validation, retries, and usage metrics.

## Current architecture

```text
Your apps / taheem_ai SDK
        |
        v
Local AI Gateway :4812
        |
        v
LM Studio :1234
        |
        +-- fast profile      -> Gemma 4 12B (candidate; not yet proven as the final fast tier)
        +-- balanced profile  -> Gemma 4 12B (historical benchmark mapping; kept reproducible)
        +-- default profile   -> GPT-OSS 20B / medium reasoning
        +-- deep profile      -> GPT-OSS 20B / medium reasoning until reasoning-level benchmark is complete
```

New applications should use `default`. `balanced` is intentionally preserved as the original Gemma benchmark profile rather than silently changing what an old benchmark command means.

## 1. Install dependencies

From the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you already have `.venv`:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Configure `.env`

Copy `.env.example` to `.env` and insert your real LM Studio token and gateway key:

```powershell
Copy-Item .env.example .env
```

Never commit `.env`.

## 3. Start LM Studio

Keep it local-only:

```powershell
lms server start --port 1234
```

Expected address:

```text
http://127.0.0.1:1234
```

## 4. Start the gateway

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 4812
```

Or:

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

## 5. Run tests

```powershell
pytest -q
```

## 6. Free-form generation

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

## 7. Structured extraction

`/v1/extract` uses LM Studio JSON-schema constrained generation and then validates the returned object again inside the gateway. If validation fails, the gateway can retry with the exact validation errors.

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

## 8. Classification

```powershell
$body = @{
    text = "Homework 4 is due Sunday at 11:59 PM."
    labels = @("assignment", "exam", "announcement", "irrelevant")
    quality = "default"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:4812/v1/classify" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

## 9. Install the Python client

```powershell
pip install -e .\clients\python
```

Basic usage:

```python
from taheem_ai import AI

ai = AI(project="itqaan")
print(ai.ask("Explain this error."))
```

Structured extraction with Pydantic:

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

## 10. Metrics

Requests are recorded in `data/gateway.db`; prompt and response content are not recorded.

```powershell
python scripts\gateway_stats.py --days 30
```

## 11. GPT-OSS reasoning benchmark

The benchmark runner now accepts an explicit reasoning override. This lets you compare the same GPT-OSS model at low, medium, and high reasoning without changing routing code:

```powershell
python benchmarks\run_benchmarks.py --quality default --reasoning low --max-output-tokens 4096 --name gptoss-low
python benchmarks\run_benchmarks.py --quality default --reasoning medium --max-output-tokens 4096 --name gptoss-medium
python benchmarks\run_benchmarks.py --quality default --reasoning high --max-output-tokens 4096 --name gptoss-high
```

Do not change the production defaults until those three runs are compared.

## Security rules

- LM Studio stays on `127.0.0.1:1234`.
- The gateway stays on `127.0.0.1:4812`.
- Never port-forward either service to the public internet.
- Keep `.env` private.
- Prompt content is not logged by default.
- Cloud fallback is not implemented/enabled in this milestone, so local failures cannot silently create API charges.

See `docs/` for architecture and API details.
