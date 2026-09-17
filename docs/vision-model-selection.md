# Vision model selection

Stage 5 treats model qualification as an evidence problem rather than a model-card decision.

The gateway already has a deterministic `vision-core-v1` regression suite. That suite proves the public Vision path still handles basic image understanding, OCR-like reading, spatial relations, multi-image input, and screenshot-like UI content. It is intentionally too small and synthetic to select the production model by itself.

Production selection therefore uses a second layer: `vision-workload-v1`.

## What is being selected

Stage 5 selects one production Vision capability behind `POST /v1/vision`.

It does **not** expose `vision-fast`, `vision-default`, or `vision-deep` yet. Model lifecycle, capability-aware routing, automatic model switching, and policy-driven tier selection belong to Stage 6. Stage 5 may benchmark multiple models and multi-model pipelines, but applications continue to see one stable Vision contract.

## Candidate policy

The initial baseline remains:

```text
google/gemma-4-12b-qat
```

It is already installed on the target machine and has passed the Stage 5 core path after correcting the LM Studio physical-batch configuration.

Serious comparison candidates should be chosen because they plausibly improve one of the actual local workload dimensions, not because they are merely newer or larger. Current candidates include:

- `qwen/qwen3-vl-8b` — small-footprint visual perception/OCR/GUI candidate;
- `google/gemma-4-26b-a4b-qat` — larger Gemma quality-ceiling candidate;
- `qwen/qwen3.8-27b` — larger multimodal reasoning/quality-ceiling candidate.

A candidate is only useful if it runs reliably on the target Legion under realistic model-load settings. Published benchmark results are useful for deciding what to test, but they do not qualify a production model for this gateway.

## Workload suite

Copy the tracked template:

```powershell
Copy-Item benchmarks\vision_workload_suite.example.json benchmarks\vision_workload.local.json
```

Keep source images under the ignored `benchmarks/vision_workload_private/` directory.

The local suite should cover the work the gateway is expected to perform in practice. A useful target is roughly 12–20 cases spanning:

- full-resolution Windows screenshots;
- VS Code/editor + terminal screenshots with small text;
- error dialogs and diagnostic UIs;
- websites and dense dark-mode interfaces;
- lecture slides;
- engineering diagrams;
- charts and tables;
- photographed/scanned documents;
- ordinary phone photos with imperfect lighting or perspective;
- game/UI overlays where small visual state matters;
- multi-image comparison or before/after reasoning.

Selected public benchmark examples may be added to the same private suite when their licenses permit local evaluation. Useful sources include GUI-grounding datasets such as ScreenSpot-Pro, document-image tasks such as DocVQA, and college-level multimodal reasoning tasks such as MMMU/MMMU-Pro. Keep the acquired fixtures local unless their license and repository policy clearly permit redistribution.

Do not change expected facts after seeing a candidate's answer. If a case definition is genuinely defective, bump the workload suite version and rerun every candidate against the new fixed suite.

## Private result boundary

Real screenshots and benchmark answers can contain private information. `run_vision_workload_benchmarks.py` therefore writes to:

```text
benchmarks/private-results/
```

by default. That directory, the local manifest, and private source images are ignored by Git.

Each run still records reproducibility metadata:

- workload-suite SHA-256;
- runner SHA-256;
- per-image SHA-256 and byte size;
- resolved Vision model;
- optional second-stage reasoning model;
- request IDs;
- request errors;
- latency;
- model load time when reported;
- time to first token when reported;
- tokens/second when reported;
- automatic expected/forbidden-term checks.

Raw model answers remain private unless deliberately redacted for a public historical record.

## Pipelines under test

The runner supports two Stage 5 experiments.

### Direct

```text
image(s) -> VLM -> final answer
```

Run:

```powershell
python benchmarks\run_vision_workload_benchmarks.py `
    --pipeline direct `
    --name gemma4-12b-direct
```

### Vision then reason

```text
image(s) -> VLM evidence extraction -> GPT-OSS/text model -> final answer
```

Run:

```powershell
python benchmarks\run_vision_workload_benchmarks.py `
    --pipeline vision-then-reason `
    --reason-quality default `
    --name gemma4-12b-to-gptoss
```

The second pipeline is an experiment, not an assumption. The VLM can become an information bottleneck: if it misses a small but critical visual fact, the reasoning model cannot recover it. It can also trigger expensive model swapping on limited GPU/VRAM systems. It should only become part of a later routing policy if measured quality gains justify the cost.

## Evaluation policy

Automatic expected/forbidden-term checks are useful regression signals, but they are not sufficient for model selection.

Every workload run creates `manual_review.json`. Review the actual images and score applicable dimensions from 0–2:

- OCR/text fidelity;
- visual/spatial accuracy;
- reasoning quality;
- unsupported-claim discipline;
- instruction following;
- multi-image correctness.

Use `null` for dimensions that genuinely do not apply to a case. Mark `production_blocker=true` for failures that should disqualify the candidate even if its averages look good, such as confidently hallucinating a critical error code or repeatedly dropping essential text.

The comparison policy deliberately avoids one weighted magic score:

1. Reject runs with request errors or manual production blockers.
2. Require completed manual review.
3. Compare visual factuality, OCR/spatial accuracy, and unsupported-claim discipline directly.
4. Compare reasoning and instruction-following quality.
5. Use latency, model-load cost, and throughput as tie-breakers when quality is materially similar.

Compare completed runs without invoking a model:

```powershell
python benchmarks\compare_vision_workloads.py `
    benchmarks\private-results\<run-a> `
    benchmarks\private-results\<run-b>
```

The comparator rejects runs with different suite hashes because they are not directly comparable.

## Qualification sequence

A production Vision decision should not be frozen until all of the following are true:

1. The candidate passes the frozen `vision-core-v1` regression suite with zero request errors.
2. The same fixed private `vision-workload-v1` suite has been run for every serious candidate/pipeline being compared.
3. Manual review is complete and no production blocker remains.
4. Runtime behavior is acceptable on the Legion, including cold/warm model behavior and model switching where applicable.
5. Real browser smoke tests cover the Playground with representative screenshots/photos/multi-image input.
6. A redacted immutable validation record is created under `benchmarks/history/` without private images or private raw answers.
7. `VISION_MODEL` and the Stage 5 documentation are updated to the selected production model.
8. CI and the final live smoke pass are green before PR #6 is merged.

## Scope boundary

Stage 5 may collect evidence about multiple candidate models and pipelines, but it should not introduce automatic model routing merely to expose the benchmark winners. That belongs to Stage 6, where model lifecycle, VRAM/resource policy, load/unload behavior, and smarter routing can be designed as one coherent system.
