# Local playground / debug UI

Stage 4 adds a browser-based local workbench at:

```text
http://127.0.0.1:4812/playground/
```

It is a development and diagnostics surface for the existing gateway. It is **not** a second AI service, a replacement client SDK, or a place where application-owned tool handlers execute.

Stage 5 extends the same workbench with a Vision panel; it does not introduce a second frontend architecture.

## Problem being solved

The gateway now exposes generation, streaming, structured extraction, classification, RAG, tool planning, vision, routing metadata, and operational metrics. Testing those paths only through PowerShell, ad-hoc Python scripts, or raw JSON becomes slow and makes it harder to compare requests, inspect metadata, observe streaming behavior, and diagnose failures.

A useful workbench therefore needs to:

- exercise the real production HTTP endpoints rather than duplicate their logic;
- keep streaming genuinely incremental;
- expose routing, token, latency, request-ID, image-preprocessing, and error information;
- make JSON-heavy structured/RAG/tool requests editable;
- make local image requests inspectable without persisting image contents;
- preserve the Stage 2 execution boundary for tools;
- avoid logging prompt/response/image content merely because the UI exists;
- remain completely local and usable without an internet connection or frontend build toolchain.

## Architecture decision

The playground is a **same-origin, zero-build HTML/CSS/JavaScript client served by FastAPI**.

This was chosen over a separate React/Vite application or CDN-based UI framework because the playground is a local engineering surface, not a standalone product. A separate frontend stack would add Node/package-lock/build/CORS/deployment complexity without improving the gateway contract. Server-rendered templates were also unnecessary because nearly all interactions are API-driven after page load.

The result has no frontend runtime package dependency and works whenever the gateway itself is running.

## Workbench design

The UI is intentionally closer to a compact developer workbench than a dashboard. It uses an edge-to-edge dark workspace, a narrow left navigation rail, two-pane request/result layouts, an optional right-side inspector, and a status bar for operational metadata. Normal panes use separators rather than decorative cards, gradients, glass effects, or permanent elevation.

The interface has eight dark colour schemes that all use the same layout and semantic tokens:

- Signal Red — default;
- Copper;
- Emerald;
- Cyan;
- Violet;
- Rose;
- Lime;
- Espresso.

The selected theme is stored locally in the browser and does not affect gateway behavior. Signal Red remains the fallback when no valid saved theme exists.

At narrower desktop widths the sidebar and inspector reduce in width. Below 900px the navigation collapses to icons, the two-pane workbench stacks vertically, and the inspector becomes an overlay. The desktop layout remains the primary target, but the workbench should stay usable at reduced viewport sizes.

## Keyboard and interaction model

The workbench supports:

```text
Ctrl+K                 Focus the command field
Cmd+K                  Focus the command field on macOS
Ctrl+Enter             Run the active workbench form
Ctrl+Shift+I           Toggle the inspector
```

The command field accepts navigation commands such as `generate`, `extract`, `classify`, `rag`, `vision`, `tools`, and `requests`, plus `inspector`, `refresh`, and `connect`.

Interactive controls expose visible keyboard focus states. Motion-heavy transitions are suppressed when the operating system requests reduced motion. On the Tools screen, the action row stays reachable while long JSON definitions scroll on desktop-sized layouts.

## Authentication and secret handling

The HTML and static assets are public to the local gateway process and contain **no gateway key**.

The user enters `X-Local-AI-Key` in the Gateway panel. The browser keeps it in `sessionStorage`, so it is scoped to the current browser tab/session rather than persisted indefinitely in `localStorage` or written to disk by the gateway.

Every sensitive API call still goes through the normal gateway authentication boundary. The Requests/debug endpoints are also authenticated.

The playground page is served with a restrictive Content Security Policy, `no-store`, `no-referrer`, MIME-sniffing protection, and frame denial. No external scripts, fonts, stylesheets, or CDNs are allowed. Local image previews use `blob:` object URLs and request payloads use base64 only when the user submits the form.

## Supported workbench views

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

The workbench intentionally does not add a new browser file-ingestion mechanism. Existing indexing APIs and `scripts/rag_ingest.py` remain the ingestion paths.

### Vision

Runs `POST /v1/vision` with one to four locally selected PNG, JPEG, or WebP images.

The panel shows thumbnail previews, prompt/system controls, output, and content-free preprocessing metadata such as source/normalized dimensions and byte counts. The browser does not persist selected files or base64 payloads.

Before the request is shown in the Inspector, image payloads are replaced with filename, media type, and byte-count metadata. This prevents a debugging feature from casually duplicating potentially large/private base64 image contents into another UI surface.

The gateway itself verifies, rotates, bounds, resizes, and metadata-strips the images before local inference. See [`vision.md`](vision.md) for the Stage 5 trust boundary.

### Tools

Runs one low-level `POST /v1/tools/turn` request with editable message history and tool definitions.

The UI **does not execute handlers**. Returned tool calls remain inert JSON. This preserves the Stage 2 rule that application-owned registries are the only execution authority.

### Requests

Displays aggregate metrics and recent content-free request metadata from the local gateway.

The backing endpoints are:

```text
GET /v1/debug/metrics?days=7
GET /v1/debug/requests?limit=50
```

They expose only operational metadata already stored in `data/gateway.db`. Prompt text, generated text, image data, RAG source text, tool definitions, tool arguments, tool results, and streamed content are not returned.

Selecting a request row opens the inspector with the operational metadata that is available. Content remains unavailable by design.

## Request inspector

The right-side inspector shows the last request body and response/event stream held in browser memory. It is closed by default and can be opened from the top bar or with `Ctrl+Shift+I`.

For Vision requests, base64 data is intentionally replaced with content-free local-file metadata before the request is rendered in the inspector.

For long streams, the browser may display a large event array. This is a debugging feature rather than a production telemetry format.

## Scope boundary

The workbench does not introduce:

- authentication beyond the existing local API key;
- remote/public hosting;
- model downloads or LM Studio process control;
- arbitrary file browsing;
- remote image fetching;
- tool execution;
- recursive agent loops;
- prompt/response/image persistence;
- a general-purpose frontend framework.

Those boundaries keep the UI useful without changing the trust model or turning the gateway into a desktop application.

## Validation

Automated tests verify that:

- the playground shell and allow-listed assets are served;
- Signal Red is the default and all eight dark themes are present;
- the Vision extension is served through the same hardened shell;
- the gateway key is not embedded in the HTML;
- security headers are present;
- unknown assets are rejected;
- keyboard/accessibility polish assets are wired into the shell;
- debug endpoints require authentication;
- recent debug rows expose operational metadata but not prompt/response/tool/RAG/image content.

CI also runs Ruff, Python compilation, and the complete pytest suite.

Before Stage 5 is merged, run one final real-browser smoke test against the real gateway and LM Studio. Recheck the existing Stage 4 surfaces, then confirm Vision image previews, one-image and multi-image requests, inspector redaction, theme behavior, keyboard submission, and narrow viewport behavior. CI cannot validate live GPU-backed multimodal inference or browser rendering.
