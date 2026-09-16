# GPT-OSS streaming production validation — 2026-09-15

This record freezes the live Stage 3 streaming validation that qualified provider-independent incremental generation for production use in Local AI Gateway.

## Immutable source run

The original generated artifacts remain unchanged at:

`benchmarks/results/20260915_215516_gptoss-streaming-v1_3b8cfc/`

Do not edit those files. If the stream contract, suite, grader, provider behavior, or gateway implementation changes materially, create a new benchmark version and a new result directory instead.

## Configuration

- Suite version: `1`
- Suite SHA-256: `93d48e3947ca26c25f82696336c134f0696209461614da1363e5386445d8f12b`
- Model: `openai/gpt-oss-20b`
- Gateway profile: `default`
- Resolved reasoning: `low`
- Max output tokens: `1024`
- Cases: `3`

## Results

- Protocol accuracy: **100%**
- Aggregate reconstruction: **100%**
- Incremental delivery: **100%**
- Request-ID consistency: **100%**
- Full-case success: **100%**
- Request errors: **0**
- Mean first-visible-text latency: **4.9463 s**
- Median first-visible-text latency: **0.7579 s**
- Mean total latency: **7.5837 s**
- Median total latency: **6.7957 s**
- Mean delta count: **131.33**

Every fixed transport case passed:

- `stream-short`: 4 deltas, 13.5198 s to first visible text, 13.6075 s total;
- `stream-long`: 310 deltas, 0.5613 s to first visible text, 6.7957 s total;
- `stream-bangla`: 80 deltas, 0.7579 s to first visible text, 2.3480 s total.

The English and Bengali cases both reconstructed exactly from ordered public `delta` events to the final `completed.text` value.

## Latency interpretation

The first case was a cold-model request. LM Studio reported **11.976 s** of model-load time before generation, and first visible text arrived at `13.5198 s`.

Once GPT-OSS was warm, first visible text arrived in `0.5613 s` and `0.7579 s` for the remaining two cases. The all-request mean is therefore intentionally retained as measured historical evidence but is cold-start-skewed; the median and warm-case values are better indicators of normal warmed perceived latency.

## Reasoning privacy

The public benchmark event stream contained no `reasoning.start`, `reasoning.delta`, or `reasoning.end` events. Hidden reasoning content therefore remained behind the provider boundary during the live run.

The final `completed` event still reported `reasoning_output_tokens` as operational metadata. Token counts are allowed; reasoning content is not.

## SDK smoke tests

Separate live smoke tests exercised both SDK paths:

- `AI.stream()` rendered text progressively through the synchronous client;
- `AsyncAI.stream()` rendered text progressively through the asynchronous client.

Both visibly produced output before generation completed, confirming that incremental delivery survived the complete LM Studio → gateway → SDK path rather than only the benchmark parser.

## Decision

Stage 3 is accepted with the following production boundary:

1. `/v1/generate/stream` is a transport variant of normal free-form generation and uses the same public request/routing model as `/v1/generate`.
2. LM Studio's native SSE vocabulary is normalized behind the gateway instead of being passed through to applications.
3. Public stream events are limited to `start`, optional `progress`, visible-text `delta`, and exactly one terminal `completed` or `error` event.
4. Hidden reasoning events are discarded and never become application-visible stream content.
5. `time_to_first_text_seconds` is the primary perceived-latency metric because provider first-token timing can include hidden reasoning.
6. Client disconnects close the upstream stream; streaming content is not persisted in operational metrics.
7. Stage 3 does not expose partial structured-output JSON, partial tool-call arguments, RAG citation structures, resumable streams, or recursive agent orchestration.

This benchmark validates the fixed Stage 3 transport suite and the implemented sync/async local SDK path. It does not grade model prose quality and does not establish guarantees for future provider versions or later streaming contracts.
