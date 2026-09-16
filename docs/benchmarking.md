# Benchmarking

## Purpose

The gateway now has several benchmark families because they answer different questions:

1. **Generation:** what can the raw local generation model do, and which reasoning profile should production use?
2. **RAG:** does the configured embedding/retrieval stack rank the expected evidence highly enough?
3. **Tool calling:** does the model choose and parameterize advertised tools correctly and synthesize safely from results?
4. **Streaming:** does incremental delivery obey the public SSE contract, reconstruct exactly, and improve perceived latency?

Those questions must stay separate. A strong model-quality score cannot prove that retrieval works, and a perfect streaming transport cannot prove that the model's answer is correct.

## Historical evidence policy

Committed benchmark result directories are immutable experiment records. Do not edit responses, scores, events, or metadata in place after a run has been used for a decision.

If grading improves, create a new result. If a prompt, expected answer, retrieval corpus, tool definition, stream contract, or grading rule changes, bump that benchmark's version and run it again.

Frozen experiment summaries live under `benchmarks/history/`.

## Generation benchmark

The generation runner calls `/v1/generate`, not the production structured endpoints. Schema-constrained decoding, local normalization, and repair retries are deliberately excluded so natural model formatting and instruction following remain measurable.

### Current generation version

The current generation suite is **v3**.

The physical `cases_*.json` files remain the v2 base definitions so historical prompts are still available. `benchmarks/current_suite.json` applies explicit v3 policy overrides. This design makes prompt changes visible and keeps the original benchmark evidence reproducible.

V3 fixes known ambiguities discovered in the September 13 reasoning experiment:

- course classification defines whether the target is an assignment, exam, administrative announcement, or coursework-irrelevant item;
- `project_005` declares the allowed generic event-type ontology;
- routing-policy cases use `fast`, `default`, and `deep` rather than the historical `balanced` terminology;
- deterministic label grading recognizes superscript exponent notation such as `O(n²)` as semantically equivalent to `O(n^2)`.

### Generation scores

The grader intentionally separates:

- **semantic correctness** — whether the answer means the right thing;
- **format correctness** — whether it uses the canonical machine representation;
- **instruction following** — whether mechanically checkable response instructions were obeyed.

A response can therefore be semantically correct while failing strict formatting. Subjective summaries and explicitly marked free-text fields remain manual rather than being awarded points through keyword matching.

### Standard generation protocol

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

### Generation artifacts

Generation runs write:

- `raw_results.json`
- `summary.json`
- `results.csv`
- `manual_review.json`
- `report.md`

The runner checkpoints after every case using atomic per-file replacement. It also records source SHA-256 hashes so the code and case policy behind a result can be identified later.

### Regrading

```powershell
python benchmarks\run_benchmarks.py `
    --regrade benchmarks\results\<run>\raw_results.json `
    --name regrade-v3
```

Regrading never performs inference and never mutates the original run. If the current prompt differs from the historical prompt, metadata marks that fact; a new grader cannot retroactively make the old prompt unambiguous.

### Comparing generation runs

```powershell
python benchmarks\compare_runs.py `
    benchmarks\results\<low>\summary.json `
    benchmarks\results\<medium>\summary.json `
    benchmarks\results\<high>\summary.json
```

The comparison helper prints semantic/format/instruction scores alongside latency, token usage, errors, and code-test totals.

## RAG benchmark

`benchmarks/rag_suite.json` uses a fixed corpus and expected document IDs. It measures retrieval ranking independently of answer generation.

Primary metrics are Recall@1/3/5, mean reciprocal rank, and query latency. A successful small-corpus validation proves that the embedding/storage/search path works on that controlled suite; it does not promise identical accuracy at much larger real-world corpus sizes.

The first production BGE-M3 run is frozen under `benchmarks/history/2026-09-14-bge-m3-rag/`.

## Tool-calling benchmark

`benchmarks/tool_suite.json` measures tool selection, argument extraction, caller-declared risk metadata, explicit/automatic no-tool behavior, final synthesis, and resistance to an instruction embedded inside tool-result data.

The benchmark never executes real application side effects. Execution authority is a separate SDK/application boundary and is validated by unit tests plus a live read-only handler smoke test.

The first production GPT-OSS tool-calling run is frozen under `benchmarks/history/2026-09-15-gptoss-tool-calling/`.

## Streaming benchmark

`benchmarks/stream_suite.json` and `run_stream_benchmarks.py` test the Stage 3 delivery contract through the **public gateway endpoint**, not LM Studio directly.

The suite validates:

- allowed event types and terminal ordering;
- multiple incremental text deltas where appropriate;
- exact concatenation of deltas to the final aggregate text;
- one consistent request ID throughout the stream;
- model/profile/final timing metadata;
- time to first **visible text**, measured at the first public `delta`;
- total request latency.

This distinction matters for reasoning models. A provider may report a first generated token before the user sees text because hidden reasoning can occur first. The Stage 3 benchmark therefore treats `time_to_first_text_seconds` as the primary perceived-latency measurement.

Streaming runs save `raw_results.json`, `summary.json`, and `report.md`. They exit non-zero unless every fixed transport case passes.

The stream suite includes English and Bengali output paths, but it does not grade the quality of the prose. Content capability remains the responsibility of the generation benchmark.

The first production GPT-OSS streaming run is frozen under `benchmarks/history/2026-09-15-gptoss-streaming/`. Its three fixed cases all passed with 100% protocol, reconstruction, incremental-delivery, request-ID-consistency, and full-case success and zero request errors. The first request was cold and spent 11.976 s loading the model before first visible text at 13.5198 s; the two warm requests reached visible text in 0.5613 s and 0.7579 s. For warmed UX expectations, the per-case warm values and 0.7579 s median are more representative than the cold-start-skewed 4.9463 s mean.

## Routing decision from the 2026-09-13 experiment

The same GPT-OSS 20B model was tested at low, medium, and high reasoning. Low was dramatically faster and used far fewer reasoning tokens while retaining strong task performance. High produced the strongest raw reliability but at substantially greater cost. Medium did not establish a compelling production niche.

Therefore:

- `default` uses GPT-OSS 20B / **low** reasoning;
- `deep` uses GPT-OSS 20B / **high** reasoning;
- `medium` remains an explicit override;
- `balanced` preserves the historical Gemma mapping;
- `fast` remains experimental until a dedicated fast-tier comparison is run.

See `docs/current-models.md` and the frozen history record for exact figures and known benchmark limitations.
