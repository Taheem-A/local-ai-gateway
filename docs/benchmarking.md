# Benchmarking

## Purpose

Benchmarks answer two different questions:

1. **What can the raw local model do?**
2. **Which model/reasoning profile should the gateway use in production?**

The runner therefore calls `/v1/generate`, not the production structured endpoints. Schema-constrained decoding, local normalization, and repair retries are deliberately excluded so natural model formatting and instruction following remain measurable.

## Historical evidence policy

Committed benchmark result directories are immutable experiment records. Do not edit responses, scores, or metadata in place after a run has been used for a decision.

If grading improves, use `--regrade` to create a new result directory. If a prompt or expected answer changes, bump the benchmark version and run the updated case again.

The September 13, 2026 GPT-OSS low/medium/high experiment is frozen under [`benchmarks/history/2026-09-13-gptoss-reasoning/`](../benchmarks/history/2026-09-13-gptoss-reasoning/).

## Current benchmark version

The current suite is **v3**.

The physical `cases_*.json` files remain the v2 base definitions so historical prompts are still available. `benchmarks/current_suite.json` applies explicit v3 policy overrides. This design makes prompt changes visible and keeps the original benchmark evidence reproducible.

V3 fixes known ambiguities discovered in the reasoning experiment:

- course classification now defines whether the target is an assignment, exam, administrative announcement, or coursework-irrelevant item;
- `project_005` declares the allowed generic event-type ontology;
- routing-policy cases use `fast`, `default`, and `deep` rather than the historical `balanced` terminology;
- deterministic label grading recognizes superscript exponent notation such as `O(n²)` as semantically equivalent to `O(n^2)`.

## Scores

The grader intentionally separates:

- **semantic correctness** — whether the answer means the right thing;
- **format correctness** — whether it uses the canonical machine representation;
- **instruction following** — whether mechanically checkable response instructions were obeyed.

A response can therefore be semantically correct while failing strict formatting. Subjective summaries and explicitly marked free-text fields remain manual rather than being awarded points through keyword matching.

## Standard run protocol

For model/reasoning comparisons:

- keep the same case version;
- keep temperature at `0.0`;
- run sequentially;
- use the same context and output-token budget;
- avoid unrelated GPU-heavy workloads;
- change only the variable being tested.

Example:

```powershell
python benchmarks\run_benchmarks.py `
    --quality default `
    --reasoning low `
    --max-output-tokens 4096 `
    --name gptoss-low-v3
```

## Result artifacts

Each run writes:

- `raw_results.json`
- `summary.json`
- `results.csv`
- `manual_review.json`
- `report.md`

The runner checkpoints after every case using atomic per-file replacement. It also records source SHA-256 hashes so the code and case policy behind a result can be identified later.

## Regrading

```powershell
python benchmarks\run_benchmarks.py `
    --regrade benchmarks\results\<run>\raw_results.json `
    --name regrade-v3
```

Regrading never performs inference and never mutates the original run. If the current prompt differs from the historical prompt, metadata marks that fact; a new grader cannot retroactively make the old prompt unambiguous.

## Comparing runs

```powershell
python benchmarks\compare_runs.py `
    benchmarks\results\<low>\summary.json `
    benchmarks\results\<medium>\summary.json `
    benchmarks\results\<high>\summary.json
```

The comparison helper prints semantic/format/instruction scores alongside latency, token usage, errors, and code-test totals.

## Routing decision from the 2026-09-13 experiment

The same GPT-OSS 20B model was tested at low, medium, and high reasoning. Low was dramatically faster and used far fewer reasoning tokens while retaining strong task performance. High produced the strongest raw reliability but at substantially greater cost. Medium did not establish a compelling production niche.

Therefore:

- `default` uses GPT-OSS 20B / **low** reasoning;
- `deep` uses GPT-OSS 20B / **high** reasoning;
- `medium` remains an explicit override;
- `balanced` preserves the historical Gemma mapping;
- `fast` remains experimental until a dedicated fast-tier comparison is run.

See `docs/current-models.md` and the frozen history record for exact figures and known benchmark limitations.
