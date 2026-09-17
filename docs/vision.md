# Vision

Stage 5 adds a bounded local multimodal capability for screenshots, photos, diagrams, and document images without changing the existing text-generation routing contract.

## Problem

Before Stage 5, applications could generate text, extract/classify structured data, retrieve local documents, stream responses, and request tools, but there was no stable way to ask the gateway about pixels.

The naive design would be to add an optional `images` field to `/v1/generate`. That is deliberately rejected because `fast`, `balanced`, `default`, and `deep` describe text-generation routing and not every model behind those profiles is guaranteed to support images. A text profile silently becoming multimodal would make application behavior depend on whichever raw model happened to implement that profile.

Stage 5 therefore treats vision as its own capability.

## Public contract

```text
POST /v1/vision
GET  /v1/vision/status
```

`POST /v1/vision` accepts one to four local images plus a prompt. Stage 5 supports:

- PNG;
- JPEG;
- WebP;
- multiple images in one turn;
- optional system instructions;
- bounded temperature/output-token controls.

Images are represented at the HTTP boundary as explicit base64 data plus a declared media type. Applications never send an LM Studio model ID.

Remote image URLs and server-side file paths are intentionally unsupported. This avoids creating an SSRF/fetching surface or allowing the gateway process to read arbitrary files on behalf of a caller.

## Why a dedicated vision model

Vision uses `VISION_MODEL` rather than a generation quality profile.

The first candidate is:

```dotenv
VISION_MODEL=google/gemma-4-12b-qat
```

This is a **candidate, not yet a production-qualified decision**. It is attractive as the first test because the same model is already present for the historical/experimental Gemma text profiles and LM Studio advertises that model as vision-capable. Reusing an installed model avoids adding another several-gigabyte model and another model-switch path before measurements show that doing so is necessary.

If it fails the fixed Stage 5 benchmark or real screenshot/photo smoke tests, the next candidates should be measured rather than guessed. `qwen/qwen3-vl-8b` and `mistralai/ministral-3-8b` are sensible follow-up candidates because LM Studio exposes vision-capable local builds in the same memory class.

Do not call any candidate the production vision model until its live Legion result is committed under `benchmarks/results/` and summarized in `benchmarks/history/`.

## Provider transport

The gateway uses LM Studio's native:

```text
POST /api/v1/chat
```

with an input array containing one text item plus verified image data URLs. The native endpoint is hidden behind `app/vision/provider.py`; application code only sees the gateway contract.

`store` is always set to `false` for Stage 5 requests. Only provider `message` output items become visible text; reasoning items are excluded from the answer while reasoning-token counts remain available as operational metadata.

Reasoning is not a Stage 5 request knob yet. Different VLM candidates expose different reasoning options, so the initial API leaves LM Studio/model-specific reasoning at its model default instead of pretending all candidates share one portable reasoning scale. A future benchmark can justify adding a stable gateway-level control if it is useful across qualified models.

## Image preprocessing and safety

The gateway does not forward arbitrary caller bytes directly into the model runtime.

For each image it:

1. strict-base64 decodes the payload;
2. enforces a per-image byte ceiling;
3. verifies the actual file format is PNG/JPEG/WebP;
4. verifies the declared media type matches the decoded file;
5. rejects animated/multi-frame inputs;
6. enforces a decoded pixel ceiling;
7. applies EXIF orientation;
8. downsizes the longest side when necessary without upscaling;
9. re-encodes pixels to strip EXIF/comments/other source metadata;
10. sends only the normalized data URL to LM Studio.

Default limits are:

```text
max images          4
max bytes/image     12 MiB
max bytes/request   24 MiB decoded
max source pixels   64,000,000
max normalized side 2,048 px
```

The pixel ceiling is intentionally independent of the final resize. A malicious or accidental decompression-bomb-sized source should be rejected before the gateway allocates an unreasonable decoded image merely because it would eventually be resized.

## Model capability gating

Before inference, the service checks LM Studio's local model inventory. The configured model must:

- be installed; and
- explicitly advertise `capabilities.vision = true`.

If either check fails, the gateway returns `VISION_MODEL_UNAVAILABLE` rather than sending the request to an arbitrary text model.

`GET /v1/vision/status` reports the configured model, whether it is installed, whether LM Studio advertises vision support, and whether an instance is currently loaded. The status call does not load or invoke the model.

## Data boundary

Operational metrics for `/v1/vision` may store:

- request ID;
- project ID;
- endpoint/capability label;
- model;
- token counts;
- timing;
- success/error code.

They do **not** store:

- image bytes/base64;
- image previews;
- prompts/system instructions;
- generated response text.

The response includes only content-free preprocessing metadata such as original/normalized dimensions and byte counts. This makes it possible to debug resize behavior without persisting the image.

## Python SDK

SDK v0.5 accepts either local paths or in-memory bytes and hides base64 transport details:

```python
from taheem_ai import AI

ai = AI(project="vision-demo")
text = ai.vision(
    "error.png",
    "Explain the error visible in this screenshot.",
)
print(text)
```

Multiple images are supported:

```python
text = ai.vision(
    ["before.png", "after.png"],
    "Compare these screenshots and identify the important change.",
)
```

`vision_response()` returns the complete metadata response. Matching async methods are exposed by `AsyncAI`.

The SDK only reads paths explicitly supplied by the local application. The HTTP API itself never accepts file paths.

## Playground

The local workbench gains a **Vision** view using the existing Stage 4 visual grammar. It provides:

- local image picker and thumbnail previews;
- multi-image requests;
- prompt/system/temperature/output-token controls;
- response text;
- image preprocessing metadata;
- the normal request/response Inspector.

The Inspector deliberately replaces image base64 with filename/media-type/byte metadata before displaying the request. Browser previews use local object URLs and are revoked when the selection changes.

## Fixed benchmark

`benchmarks/vision_suite.json` defines six deterministic synthetic cases covering:

- colored-shape recognition;
- visible text reading;
- table reading;
- spatial relation understanding;
- multiple-image reading/reasoning;
- screenshot-like UI/error reading.

`run_vision_benchmarks.py` creates the images with pinned Pillow code at run time, sends them through the **public `/v1/vision` endpoint**, and saves the exact generated fixtures with the result. The runner records both suite and runner SHA-256 hashes so later runs can be tied to the exact case definitions and rendering logic.

The initial qualification gate is deliberately simple and strict:

```text
100% of explicit visible facts present
0 request errors
one consistent model across the run
```

This small suite proves that the end-to-end Stage 5 path handles the core visual workloads it was designed for. It does not claim universal OCR accuracy, broad visual reasoning superiority, or benchmark dominance over other VLMs.

Run it with:

```powershell
python benchmarks\run_vision_benchmarks.py `
    --name gemma4-12b-qat-vision-v1
```

If the candidate fails, preserve that result, change `VISION_MODEL`, restart the gateway, and run the same frozen suite against the next candidate. Do not edit expected terms after seeing a model answer.

## Scope boundary

Stage 5 intentionally does **not** add:

- remote image fetching;
- arbitrary gateway-side file browsing;
- video input;
- vision streaming;
- schema-constrained visual extraction;
- vision + tool execution/orchestration;
- recursive agents;
- an OCR-only pipeline;
- automatic OCR ingestion for scanned RAG PDFs.

Those features have different correctness and security contracts and should only be added when a real application requires them.
