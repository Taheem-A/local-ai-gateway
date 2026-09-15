# Streaming

## Problem

Non-streaming generation makes an application wait for the complete model response before it can render any text. For longer local generations, that turns otherwise acceptable inference time into poor perceived latency.

Streaming has a second architectural problem: LM Studio exposes provider-specific SSE event names, including hidden reasoning deltas. Passing those events directly to applications would couple every client to LM Studio and risk exposing content that the gateway intentionally keeps private.

Stage 3 therefore needs to provide incremental **user-visible text** while preserving the gateway as the provider boundary.

## Options considered

### Raw provider SSE passthrough

Simple, but rejected. LM Studio's native stream includes provider-specific lifecycle, reasoning, message, tool, and error events. Clients would become LM Studio clients rather than Local AI Gateway clients, and reasoning deltas could leak.

### WebSockets

Useful for long-lived bidirectional sessions, but unnecessary for a request whose primary flow is server-to-client text. WebSockets also add connection lifecycle and reconnection complexity that Stage 3 does not need.

### NDJSON/chunked JSON

Technically workable, but it invents a transport when Server-Sent Events already provide standardized framing and named events.

### Gateway-owned SSE

**Decision:** consume LM Studio's native SSE internally, then expose a small provider-independent SSE contract from the gateway.

## Endpoint

`POST /v1/generate/stream`

The request body is exactly the same `GenerateRequest` used by `/v1/generate`:

```json
{
  "prompt": "Explain turnbuckles briefly.",
  "quality": "default",
  "reasoning": null,
  "temperature": 0.2,
  "max_output_tokens": 2048
}
```

Authentication and project attribution use the same headers as the rest of the gateway.

The response media type is `text/event-stream`.

## Public event contract

Every event uses both a named SSE event and a matching JSON `type` field.

### `start`

Emitted immediately after the request has passed gateway validation/authentication and the stream begins.

```text
event: start
data: {"type":"start","request_id":"...","model":"openai/gpt-oss-20b","profile":"default","quality":"default","reasoning":"low"}
```

This event does not claim that model inference has started; a cold model may still need to load.

### `progress`

Optional normalized lifecycle information. Current phases are:

- `model_loading`
- `prompt_processing`

Each event has a state of `started`, `running`, or `completed`. A provider may omit progress values, and future providers are not required to expose these events.

```text
event: progress
data: {"type":"progress","request_id":"...","phase":"model_loading","state":"running","progress":0.65}
```

Applications must treat progress events as optional UX hints, not correctness signals.

### `delta`

One user-visible text fragment.

```text
event: delta
data: {"type":"delta","request_id":"...","text":"The current"}
```

Concatenating all `delta.text` values in order yields the streamed response. The benchmark verifies that the reconstructed text matches the final aggregate.

### `completed`

Exactly one successful terminal event.

It contains the complete final text plus routing/token/timing metadata:

```json
{
  "type": "completed",
  "request_id": "...",
  "text": "The complete answer.",
  "model": "openai/gpt-oss-20b",
  "profile": "default",
  "quality": "default",
  "reasoning": "low",
  "input_tokens": 120,
  "output_tokens": 80,
  "reasoning_output_tokens": 20,
  "tokens_per_second": 45.1,
  "time_to_first_token_seconds": 0.35,
  "time_to_first_text_seconds": 0.62,
  "model_load_time_seconds": null,
  "total_latency_seconds": 2.4
}
```

`time_to_first_token_seconds` is the provider's token-level metric and can include hidden reasoning. `time_to_first_text_seconds` is measured by the gateway at the first public `delta` and is therefore the better perceived-latency metric for applications.

### `error`

Authentication and request-schema failures occur before streaming starts and use the normal HTTP/JSON gateway error envelope.

Once SSE headers have been committed, a provider/runtime failure cannot change the HTTP status code. It is therefore sent in-band:

```text
event: error
data: {"type":"error","request_id":"...","error":{"code":"LMSTUDIO_UNAVAILABLE","message":"...","details":null}}
```

An `error` event is terminal. SDK clients translate it to `AIError`.

## Reasoning privacy

LM Studio's native `/api/v1/chat` stream can emit `reasoning.start`, `reasoning.delta`, and `reasoning.end`. The provider adapter explicitly drops all of them.

The public gateway stream only exposes:

- `start`
- `progress`
- `delta`
- `completed`
- `error`

Unknown future LM Studio lifecycle events are ignored rather than automatically becoming public API.

## Why the native LM Studio stream is used internally

The existing `/v1/generate` path uses LM Studio's native `/api/v1/chat` endpoint. Its streaming mode ends with `chat.end`, which contains the aggregated result and generation statistics corresponding to the non-streaming response.

Using the same provider endpoint keeps streamed and non-streamed free-form generation aligned instead of maintaining two different prompt/template stacks.

## Python SDK

SDK v0.4 adds two levels of API.

### Text-only streaming

```python
from taheem_ai import AI

ai = AI(project="demo")
for text in ai.stream("Explain DNS in five sentences."):
    print(text, end="", flush=True)
```

Async:

```python
from taheem_ai import AsyncAI

ai = AsyncAI(project="demo")
async for text in ai.stream("Explain DNS in five sentences."):
    print(text, end="", flush=True)
```

### Lifecycle events

Use `stream_events()` when progress or final metadata matters:

```python
for event in ai.stream_events("Explain DNS."):
    if event["type"] == "delta":
        print(event["text"], end="", flush=True)
    elif event["type"] == "completed":
        print("\nTTFT-visible:", event["time_to_first_text_seconds"])
```

Stopping iteration closes the HTTP response, which in turn closes the gateway stream and upstream LM Studio request.

## Cancellation and disconnects

When the client disconnects before completion, the gateway closes the provider async generator and records the request as failed with `CLIENT_DISCONNECTED`. No prompt or partial response text is persisted in metrics.

Streaming is not resumable in v1. The endpoint is a POST request with request-specific generation state, so the gateway does not emit SSE replay IDs or promise automatic reconnection.

## Metrics and privacy

Successful streams are recorded once, at `completed`. Failed/disconnected streams are recorded once with their error code.

Metrics retain operational data only: model/profile, token counts, provider first-token timing, model-load timing when available, total latency, project ID, and success/failure. Prompt text and streamed text are not stored.

## Deliberately deferred

Stage 3 does **not** stream:

- partial schema-constrained extraction/classification JSON;
- partial tool-call argument fragments;
- RAG citation structures;
- recursive agent/tool orchestration;
- resumable/replayable streams.

Those require their own semantic contracts. In particular, partial tool arguments must never be treated as executable authority, and multi-step agent events belong to Stage 7.
