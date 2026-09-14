# Architecture

## Purpose

The gateway is a stable abstraction between personal applications and local model runtimes. Applications request capabilities such as free-form generation, extraction, or classification. They select a public profile (`fast`, `default`, or `deep`) rather than a raw model ID.

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
   +-- profile + reasoning routing
   +-- structured-output validation/retries
   +-- non-content operational metrics
   |
   v
LM Studio (:1234)
   |
   v
Local model on GPU
```

## Profiles

- `fast`: current experimental Gemma 4 12B mapping. It is not yet the proven final fast-tier winner.
- `balanced`: historical Gemma benchmark profile preserved only for reproducibility.
- `default`: GPT-OSS 20B with **low** reasoning. This is the normal application profile.
- `deep`: GPT-OSS 20B with **high** reasoning. This is reserved for tasks that justify substantially more latency and reasoning tokens.

The low/high decision comes from the frozen September 2026 reasoning benchmark. Medium reasoning remains available as an explicit per-request override rather than occupying a production profile.

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

## Metrics

Operational metadata is stored in SQLite under `data/gateway.db`. Records include project ID, endpoint, profile, model, reasoning level, token counts, latency, attempts, success/failure, and error code.

Prompt and response contents are intentionally not stored by the metrics layer.

## Failure handling

Gateway-owned failures use stable error codes such as `AUTH_FAILED`, `INVALID_REQUEST`, `LMSTUDIO_UNAVAILABLE`, and `OUTPUT_INVALID`. Provider failures are recorded in the metrics database before they are translated to gateway errors.

## Security boundary

Both services bind only to loopback:

- LM Studio: `127.0.0.1:1234`
- Gateway: `127.0.0.1:4812`

Remote access, if added later, must use a private authenticated network rather than public port forwarding.

## Benchmarks versus production safeguards

Benchmark runs deliberately call `/v1/generate` so raw model formatting, instruction following, and reasoning behavior remain measurable. Production structured endpoints add schema constraints, normalization, and repair retries. A raw benchmark format score therefore should not be interpreted as the production structured-output success rate.

Historical benchmark artifacts are immutable. The current suite is versioned separately from prior result directories.

## Future layers

Later milestones can add embeddings/RAG, vision, tools, bounded agents, caching, queueing, private remote access, and explicit paid fallback without changing the core application contract.
