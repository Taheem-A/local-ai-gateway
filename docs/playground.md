# Local playground / debug UI

Stage 4 adds a browser-based local playground at:

```text
http://127.0.0.1:4812/playground/
```

It is a development and diagnostics surface for the existing gateway. It is **not** a second AI service, a replacement client SDK, or a place where application-owned tool handlers execute.

## Problem being solved

The gateway now exposes generation, streaming, structured extraction, classification, RAG, tool planning, routing metadata, and operational metrics. Testing those paths only through PowerShell, ad-hoc Python scripts, or raw JSON becomes slow and makes it harder to compare requests, inspect metadata, observe streaming behavior, and diagnose failures.

A useful Stage 4 interface therefore needs to:

- exercise the real production HTTP endpoints rather than duplicate their logic;
- keep streaming genuinely incremental;
- expose routing, token, latency, request-ID, and error information;
- make JSON-heavy structured/RAG/tool requests editable;
- preserve the Stage 2 execution boundary for tools;
- avoid logging prompt/response content merely because the UI exists;
- remain completely local and usable without an internet connection or frontend build toolchain.

## Architecture decision

The playground is a **same-origin, zero-build HTML/CSS/JavaScript client served by FastAPI**.

This was chosen over a separate React/Vite application or CDN-based UI framework because the playground is a local engineering surface, not a standalone product. A separate frontend stack would add Node/package-lock/build/CORS/deployment complexity without improving the gateway contract. Server-rendered templates were also unnecessary because nearly all interactions are API-driven after page load.

The result has no new runtime package dependency and works whenever the gateway itself is running.

## Authentication and secret handling

The HTML and static assets are public to the local gateway process and contain **no gateway key**.

The user enters `X-Local-AI-Key` in the connection panel. The browser keeps it in `sessionStorage`, so it is scoped to the current browser tab/session rather than persisted indefinitely in `localStorage` or written to disk by the gateway.

Every sensitive API call still goes through the normal gateway authentication boundary. The new debug endpoints are also authenticated.

The playground page is served with a restrictive Content Security Policy, `no-store`, `no-referrer`, MIME-sniffing protection, and frame denial. No external scripts, fonts, stylesheets, or CDNs are allowed.

## Supported panels

### Generate

Runs either:

- `POST /v1/generate`, or
- `POST /v1/generate/stream`.

Streaming uses the public Stage 3 SSE contract and renders only user-visible `delta` events. Progress events and final metadata remain available in the inspector. A Stop button aborts the browser request so disconnect/cancellation behavior can be tested.

### Extract

Runs `POST /v1/extract` with an editable JSON Schema and the same quality/reasoning/output-token controls as the public endpoint.

### Classify

Runs `POST /v1/classify` with editable labels and the normal bounded structured-output retry settings.

### RAG

Supports:

- collection inspection through `GET /v1/rag/collections`;
- raw semantic retrieval through `POST /v1/rag/search`;
- grounded generation through `POST /v1/rag/answer`.

The Stage 4 UI intentionally does not add a new browser file-ingestion mechanism. Existing indexing APIs and `scripts/rag_ingest.py` remain the ingestion paths.

### Tools

Runs one low-level `POST /v1/tools/turn` request with editable message history and tool definitions.

The UI **does not execute handlers**. Returned tool calls remain inert JSON. This preserves the Stage 2 rule that application-owned registries are the only execution authority.

### Debug

Displays gateway/LM Studio status, routing profiles, recent aggregate metrics, and recent request metadata.

The backing endpoints are:

```text
GET /v1/debug/metrics?days=7
GET /v1/debug/requests?limit=50
```

They expose only operational metadata already stored in `data/gateway.db`. Prompt text, generated text, RAG source text, tool definitions, tool arguments, tool results, and streamed content are not returned.

## Request inspector

The right-side inspector shows the last request body and response/event stream held in browser memory. It is intentionally client-side only and is not persisted by the gateway.

For long streams, the browser may display a large event array. This is a debugging feature rather than a production telemetry format.

## Scope boundary

Stage 4 does not introduce:

- authentication beyond the existing local API key;
- remote/public hosting;
- model downloads or LM Studio process control;
- arbitrary file browsing;
- tool execution;
- recursive agent loops;
- prompt/response persistence;
- a general-purpose frontend framework.

Those boundaries keep the UI useful without changing the trust model or turning the gateway into a desktop application.

## Validation

Automated tests verify that:

- the playground shell and assets are served;
- the gateway key is not embedded in the HTML;
- security headers are present;
- unknown assets are rejected;
- debug endpoints require authentication;
- recent debug rows expose operational metadata but not prompt/response/tool/RAG content.

A final local smoke test should still be run against the real gateway and LM Studio before Stage 4 is merged, because CI cannot validate browser rendering or live GPU-backed streaming.
