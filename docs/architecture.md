# Architecture

## Purpose

The gateway is a stable abstraction between personal applications and local model runtimes. Applications request capabilities such as free-form generation, extraction, or classification. They do not select raw model IDs.

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
   +-- authentication
   +-- profile routing
   +-- structured-output validation/retries
   +-- metrics
   |
   v
LM Studio (:1234)
   |
   v
Local model on GPU
```

## Profiles

- `fast`: backwards-compatible lightweight candidate profile. It currently points to Gemma 4 12B and must not be treated as a proven fast winner until the dedicated fast-tier benchmark is run.
- `default`: GPT-OSS 20B with medium reasoning, based on the completed benchmark.
- `deep`: currently the same GPT-OSS 20B / medium configuration. The profile exists now so applications can remain stable while low/medium/high reasoning is benchmarked later.
- `balanced`: API compatibility alias for `default`.

Applications should request a profile, never a model name.

## Structured output

Structured endpoints use two layers of enforcement:

1. LM Studio's OpenAI-compatible `response_format=json_schema` constrained generation.
2. Local `jsonschema` validation after generation.

The gateway performs conservative schema-directed normalization for equivalent representations such as dates and times. It never repairs a fact by guessing a different factual value.

If validation fails, the gateway retries at most the caller-configured attempt count (default two), including the exact validation failures in the repair prompt.

## Metrics

Operational metadata is stored in SQLite under `data/gateway.db`. The database records model/profile, token counts, latency, attempts, success/failure, and project ID. Prompt contents are intentionally not stored by default.

## Security boundary

Both services bind only to loopback. Remote access, if ever added, must use a private authenticated network rather than public port forwarding.

## Future layers

Later milestones can add embeddings/RAG, vision, tools, bounded agents, caching, queueing, private remote access, and explicit paid fallback without changing application-facing model names.
