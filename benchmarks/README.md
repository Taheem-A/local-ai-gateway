# Benchmarks

The benchmark system separates generation capability, retrieval capability, tool-calling behavior, and streaming transport behavior. Generation benchmarks measure raw model behavior through `/v1/generate`; the RAG benchmark measures dense retrieval ranking through `/v1/rag/search`; the tool benchmark measures whether the model selects and parameterizes advertised tools correctly through `/v1/tools/turn`; and the streaming benchmark measures whether incremental delivery through `/v1/generate/stream` obeys the gateway protocol. Keeping these dimensions separate prevents one strong subsystem from masking another weak one.

## Versioning policy

A committed benchmark run is evidence and is treated as immutable.

When a prompt, expected answer, grading rule, corpus, query, tool definition, stream contract, or runner behavior changes in a way that affects comparability:

1. bump the relevant benchmark version,
2. update the current benchmark policy and tests,
3. leave old result directories unchanged,
4. document why the version changed.

The original generation v2 base case files remain in `cases_core.json`, `cases_project.json`, and `cases_long_context.json`. The current generation benchmark is **v3**, implemented as explicit overrides in `current_suite.json`. This keeps the exact v2 prompts available for reproducing historical reasoning runs while allowing future runs to use clarified tasks.

Historical experiments are summarized under `history/`.

## Generation benchmark v3

Benchmark v3 addresses issues discovered during the September 2026 GPT-OSS reasoning comparison:

- classification explicitly asks for the referenced **course-item type**, not the grammatical form of the message;
- `irrelevant` is defined relative to course instruction, assessment, scheduling, or administration;
- university `event_type` uses a declared generic ontology;
- routing-policy cases use the production names `fast`, `default`, and `deep`;
- label grading recognizes mathematically equivalent superscript exponents such as `O(n²)` and `O(n^2)` while still scoring strict formatting separately.

Run the current generation benchmark:

```powershell
python benchmarks\run_benchmarks.py `
    --quality default `
    --reasoning low `
    --max-output-tokens 4096 `
    --name gptoss-low-v3
```

Requests run sequentially so GPU contention does not distort timing comparisons.

## RAG retrieval benchmark v1

`rag_suite.json` contains a small fixed corpus plus queries with expected document IDs. It includes English, Bengali, and Arabic cases.

```powershell
python benchmarks\run_rag_benchmarks.py --name bge-m3-rag-v1
```

Reported metrics are Recall@1/3/5, mean reciprocal rank, and mean/median retrieval latency. The runner exits non-zero if Recall@5 is below 100%.

The first production BGE-M3 validation is frozen under `history/2026-09-14-bge-m3-rag/`.

## Tool-calling benchmark v1

`tool_suite.json` measures the Stage 2 abstraction independently from real side-effect execution. The suite covers:

- selecting the correct tool among distractors;
- typed and enum argument extraction;
- preserving caller-declared risk metadata;
- `tool_choice=required`;
- explicit and automatic no-tool behavior;
- synthesis after a tool result;
- ignoring a prompt-injection instruction embedded inside a tool result.

Run it against the production local generation profile:

```powershell
python benchmarks\run_tool_benchmarks.py `
    --quality default `
    --name gptoss-tool-calling-v1
```

The runner reports selection accuracy, argument accuracy, risk-annotation accuracy, synthesis-constraint accuracy, full-case success rate, request errors, and mean/median latency. It also records the suite version/SHA-256, resolved model/profile/reasoning, and output-token budget. The benchmark only exercises model/gateway tool planning and synthesis; application handlers are tested separately by the SDK unit tests and live smoke test.

The first production GPT-OSS validation is frozen under `history/2026-09-15-gptoss-tool-calling/`. The immutable source run achieved 100% selection, argument, risk-annotation, synthesis-constraint, and full-case success across all eight fixed cases with zero request errors on GPT-OSS 20B / `default` / low reasoning. Its overall mean latency was 4.8203 s because the first request took 24.8698 s; the remaining seven requests averaged about 1.99 s and the run median was 2.0042 s.

## Streaming benchmark v1

`stream_suite.json` tests the Stage 3 transport contract rather than free-form answer quality. It includes short and longer English output plus a Bengali path.

```powershell
python benchmarks\run_stream_benchmarks.py `
    --quality default `
    --name gptoss-streaming-v1
```

The runner verifies:

- `start` is the first public event and exactly one `completed` event is terminal;
- only the gateway-owned public event types are exposed;
- output arrives through incremental `delta` events rather than only as a final blob;
- concatenated deltas reconstruct exactly to the final aggregate text;
- one request ID is preserved across every event;
- measured time to first visible text is valid and no greater than total latency;
- final model/profile/timing metadata is present.

Reported metrics include protocol accuracy, aggregate-match accuracy, incremental-delivery accuracy, request-ID consistency, full-case success, request errors, mean/median time to first visible text, mean/median total latency, and mean delta count.

The benchmark intentionally does **not** grade whether the model's prose is semantically excellent. Generation quality already has its own suite; Stage 3 is about delivery correctness and perceived latency.

A live result is not production evidence until its result directory is committed unchanged and summarized under `history/`.

## Saved artifacts

Generation runs receive a unique directory under `benchmarks/results/` containing `raw_results.json`, `summary.json`, `results.csv`, `manual_review.json`, and `report.md`.

RAG, tool-calling, and streaming runs save `raw_results.json`, `summary.json`, and `report.md` because their fixed suites are mechanically graded.

Committed benchmark artifacts are immutable. Create a new run when a suite or implementation changes; do not rewrite a historical result to improve its score.

## Manual review

Summary semantics and explicitly marked free-text generation fields remain manual. Mechanical constraints such as word limits, sentence counts, bullet counts, JSON structure, canonical date/time formatting, tool names, tool arguments, and stream event ordering are checked deterministically.

Do not rewrite expected answers after seeing a model response merely to improve a score.

## Curated code execution

The fixed Python coding cases execute in a temporary directory with a separate `python -I` process, a five-second timeout, and a reduced child environment. This provides process isolation, **not** a security sandbox. Never use the helper to execute arbitrary external prompts or untrusted benchmark suites.

## Regrade without model requests

```powershell
python benchmarks\run_benchmarks.py `
    --regrade benchmarks\results\<run>\raw_results.json `
    --name regrade-v3
```

Regrading creates a new result directory and never mutates the source run.

## Compare completed generation runs

```powershell
python benchmarks\compare_runs.py `
    benchmarks\results\<run-a>\summary.json `
    benchmarks\results\<run-b>\summary.json
```

The comparison helper reads summary artifacts only. It never invokes a model or changes saved results.

## Frozen GPT-OSS reasoning experiment

See [`history/2026-09-13-gptoss-reasoning/README.md`](history/2026-09-13-gptoss-reasoning/README.md) for the low/medium/high experiment that selected:

- `default` -> GPT-OSS 20B / low reasoning;
- `deep` -> GPT-OSS 20B / high reasoning.

## Validate benchmark code

Benchmark regressions are included in the normal project test suite:

```powershell
pytest -q
```

They use mock/deterministic local components and do not consume live LM Studio inference. Live RAG, tool-calling, and streaming runs must still be executed on the target local models before those configurations are considered production-validated.
