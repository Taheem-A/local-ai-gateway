# Benchmarks

The benchmark system separates generation capability from retrieval capability. Generation benchmarks measure raw model behavior through `/v1/generate`; the RAG benchmark measures dense retrieval ranking through `/v1/rag/search`. Keeping these dimensions separate prevents a strong generation model from masking a weak retriever, or vice versa.

## Versioning policy

A committed benchmark run is evidence and is treated as immutable.

When a prompt, expected answer, grading rule, corpus, query, or runner behavior changes in a way that affects comparability:

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
- university `event_type` uses a declared generic ontology, so `lecture` is no longer compared against an underspecified free-text field;
- routing-policy cases use the production names `fast`, `default`, and `deep`;
- label grading recognizes mathematically equivalent superscript exponents such as `O(n²)` and `O(n^2)` while still scoring strict formatting separately.

The suite reports three independent dimensions:

- `semantic_correct`: whether the answer conveys the expected information under explicit normalization rules;
- `format_correct`: whether output is in the benchmark's canonical machine representation;
- `instruction_following`: whether mechanically checkable output instructions were followed.

`null` semantic results require manual review rather than being guessed as pass/fail.

Run the current generation benchmark:

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

## RAG retrieval benchmark v1

`rag_suite.json` contains a small fixed corpus plus queries with expected document IDs. It includes English, Bengali, and Arabic cases because the preferred BGE-M3 embedding model is being selected partly for multilingual retrieval.

Run it after the configured embedding model is installed and available through LM Studio:

```powershell
python benchmarks\run_rag_benchmarks.py --name bge-m3-rag-v1
```

The runner:

1. creates a unique temporary RAG collection;
2. indexes the fixed corpus through `/v1/rag/index`;
3. sends each query to `/v1/rag/search` sequentially;
4. records the rank of the expected document and query latency;
5. deletes the temporary collection unless `--keep-collection` is supplied;
6. writes a new immutable result directory.

Reported metrics are:

- **Recall@1** — expected document ranked first;
- **Recall@3** and **Recall@5** — expected document appears in the first 3/5 hits;
- **MRR** — mean reciprocal rank, rewarding higher placement;
- mean and median search latency.

The runner exits non-zero if Recall@5 is below 100% so an obviously broken retrieval configuration is hard to overlook. Recall@1 and MRR remain the more useful metrics for comparing otherwise functional embedding configurations.

This benchmark intentionally evaluates retrieval only. RAG answer generation should be assessed separately because answer quality also depends on GPT-OSS, the retrieved context budget, and structured generation.

## Saved artifacts

Generation runs receive a unique directory under `benchmarks/results/` containing:

- `raw_results.json` — source responses, request settings without credentials, grading details, and performance metrics;
- `summary.json` — aggregate and per-category scores;
- `results.csv` — spreadsheet-friendly case rows;
- `manual_review.json` — the semantic-review queue;
- `report.md` — a readable case/score summary.

RAG retrieval runs save `raw_results.json`, `summary.json`, and `report.md` because the expected-document rank is fully deterministic and requires no manual semantic review.

Generation files are replaced atomically after each case, so an interrupted process preserves completed work. `raw_results.json` is the primary recovery artifact.

Generation runs also record SHA-256 hashes of the benchmark policy, base cases, runner/grader modules, and gateway Python source used at execution time. Future RAG benchmark revisions should preserve the same immutable-evidence principle.

## Manual review

Summary semantics and explicitly marked free-text generation fields remain manual. Mechanical constraints such as word limits, sentence counts, bullet counts, JSON structure, and canonical date/time formatting are checked deterministically.

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

The three original result directories remain unchanged.

## Validate benchmark code

Benchmark regressions are included in the normal project test suite:

```powershell
pytest -q
```

They use mock/deterministic local components and do not consume live LM Studio inference. The live RAG retrieval run must still be executed on the actual local embedding model before a model configuration is considered production-validated.
