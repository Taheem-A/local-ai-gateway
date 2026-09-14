# Benchmarks

The benchmark system measures raw model capability separately from the production gateway safeguards. Live benchmark cases intentionally call `/v1/generate` rather than `/v1/extract` or `/v1/classify`; otherwise JSON-schema constraints and repair retries would hide the model's natural formatting and instruction-following behavior.

## Versioning policy

A committed benchmark run is evidence and is treated as immutable.

When a prompt, expected answer, grading rule, or runner behavior changes in a way that affects comparability:

1. bump the benchmark version,
2. update the current benchmark policy and tests,
3. leave old result directories unchanged,
4. document why the version changed.

The original v2 base case files remain in `cases_core.json`, `cases_project.json`, and `cases_long_context.json`. The current benchmark is **v3**, implemented as explicit overrides in `current_suite.json`. This keeps the exact v2 prompts available for reproducing historical reasoning runs while allowing future runs to use clarified tasks.

Historical experiments are summarized under `history/`.

## Current v3 fixes

Benchmark v3 addresses issues discovered during the September 2026 GPT-OSS reasoning comparison:

- classification explicitly asks for the referenced **course-item type**, not the grammatical form of the message;
- `irrelevant` is defined relative to course instruction, assessment, scheduling, or administration;
- university `event_type` uses a declared generic ontology, so `lecture` is no longer compared against an underspecified free-text field;
- routing-policy cases use the production names `fast`, `default`, and `deep`;
- label grading recognizes mathematically equivalent superscript exponents such as `O(n²)` and `O(n^2)` while still scoring strict formatting separately.

The suite continues to report three independent dimensions:

- `semantic_correct`: whether the answer conveys the expected information under explicit normalization rules;
- `format_correct`: whether output is in the benchmark's canonical machine representation;
- `instruction_following`: whether mechanically checkable output instructions were followed.

`null` semantic results require manual review rather than being guessed as pass/fail.

## Run the current benchmark

From the repository root:

```powershell
python benchmarks\run_benchmarks.py `
    --quality default `
    --reasoning low `
    --max-output-tokens 4096 `
    --name gptoss-low-v3
```

Useful options:

- `--category structured_extraction` runs one category only;
- `--reasoning low|medium|high` overrides the selected profile's configured reasoning level;
- `--max-output-tokens` applies the same total generation ceiling to every selected case;
- `--skip-code-tests` prevents generated Python from executing;
- `--regrade <raw_results.json>` regrades stored responses without invoking a model.

Requests run sequentially so GPU contention does not distort timing comparisons.

## Saved artifacts

Every run receives a unique directory under `benchmarks/results/` containing:

- `raw_results.json` — source responses, request settings without credentials, grading details, and performance metrics;
- `summary.json` — aggregate and per-category scores;
- `results.csv` — spreadsheet-friendly case rows;
- `manual_review.json` — the semantic-review queue;
- `report.md` — a readable case/score summary.

Files are replaced atomically after each case. An interrupted process therefore preserves completed work. `raw_results.json` is the primary recovery artifact.

Runs also record SHA-256 hashes of the benchmark policy, base cases, runner/grader modules, and gateway Python source used at execution time.

## Manual review

Summary semantics and explicitly marked free-text fields remain manual. Mechanical constraints such as word limits, sentence counts, bullet counts, JSON structure, and canonical date/time formatting are still checked deterministically.

A review should evaluate:

- factual accuracy,
- coverage of required concepts,
- unsupported claims,
- whether a differently worded answer is genuinely equivalent.

Do not rewrite expected answers after seeing a model response merely to improve a score.

## Curated code execution

The four fixed Python coding cases execute in a temporary directory with a separate `python -I` process, a five-second timeout, and a reduced child environment. This provides process isolation, **not** a security sandbox. Never use the helper to execute arbitrary external prompts or untrusted benchmark suites.

## Regrade without model requests

```powershell
python benchmarks\run_benchmarks.py `
    --regrade benchmarks\results\<run>\raw_results.json `
    --name regrade-v3
```

Regrading creates a new result directory and never mutates the source run. The metadata records whether the historical prompts match the current suite. A regrade cannot make a rewritten v3 prompt directly comparable to the old v2 prompt that generated a stored answer.

## Compare completed runs

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

The three original result directories remain unchanged.

## Validate the benchmark code

The benchmark regressions are included in the normal project test suite:

```powershell
pytest -q
```

They use a mock gateway and do not consume local-model inference.
