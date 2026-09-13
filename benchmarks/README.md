# Benchmark v2

Run from the local-ai-gateway directory, using the existing Python environment:

```powershell
python benchmarks\run_benchmarks.py --quality balanced --category structured_extraction --name gemma-extraction-test
```

Omit `--category` to run all 40 cases. Requests run sequentially. The runner uses the existing `.env`, `X-Local-AI-Key` authentication, `/health`, and `/v1/generate` request/response contract. No gateway changes or additional dependencies are required.

## Scores

- `semantic_correct`: whether the answer matches the expected information under the case's explicit normalization rules. `null` means manual review is required, including incomplete JSON or ambiguous prose.
- `format_correct`: bare output, expected JSON keys/types, and canonical date/time representation where configured through normalization. This is the benchmark's canonical representation, even when a prompt does not explicitly demand ISO dates or 24-hour times.
- `instruction_following`: mechanically checked output instructions. For example, an alternative date representation can pass instructions when ISO was not requested, while `long_002` explicitly requires ISO dates and 24-hour times. Key order is enforced for `instruction_005` only. Summary scores cover mechanical constraints; semantic instructions such as avoiding invented facts remain part of manual review.

Statuses are `pass`, `pass_with_format_issue`, `fail`, `manual`, or `error`. Compatibility field `passed` now represents semantic correctness, not strict overall compliance. Each dimension has its own denominator; unknown scores and request errors are excluded. Inspect error and manual counts alongside percentages.

Normalization is configured by field path in `expected.normalize`; `*` addresses array elements. Arrays retain order and cardinality. Keys are exact except for case-specific aliases in `expected.key_aliases`. Extra/missing fields are not silently ignored. Number strings may match numeric values but fail numeric schema requirements; booleans are never treated as numbers. Text normalization collapses whitespace, ignores case, and permits `Problem Set #2` versus `Problem Set 2`; it does not equate arbitrary synonyms. Identifier fields are kept exact. Dates require a year and an unambiguous ISO or named-month format. ET/Eastern Time are equivalent, but EST and EDT remain distinct.

Labels accept exact labels or simple affirmative wrappers such as `The correct classification is assignment.` A wrong valid label passes format and fails semantics. Negation, alternative answers, and other ambiguous prose require review. Numeric answers accept bare decimal/scientific numbers or simple answer wrappers; tolerance applies only to semantics. Multiple candidate numbers are not searched for an expected-value match.

Complete JSON embedded in prose or a Markdown fence can be graded semantically while failing format. Truncated JSON, duplicate keys, non-finite values, or multiple candidate documents are sent to review. The grader never fills missing content from the expected answer.

## Code and subjective cases

The four existing curated Python cases retain all 13 execution tests. Code runs in a temporary directory using a separate `python -I` process and a five-second timeout. Gateway credentials are removed from the child environment. This is process isolation, not a security sandbox; use `--skip-code-tests` to disable execution. Do not use this runner to execute arbitrary untrusted benchmark suites.

Summary semantics always require manual review. Word limits, sentence counts, and bullet constraints are checked automatically; sentence splitting is heuristic. `manual_review.json` includes the prompt, response, rubric, mechanical results, and blank reviewer fields. Review accuracy, required concepts, and unsupported claims. Editing this file records your review but does not automatically change summary scores; retain the reviewed copy separately before any rerun or regrade.

## Saved runs and recovery

Every run gets a unique directory under `benchmarks/results`. After every case, the runner atomically replaces each of:

- `raw_results.json`: original response and metrics, prompt, request without credentials, grading policy, per-case results.
- `summary.json`: separate dimension scores, per-category scores, code tests, timings, and tokens.
- `results.csv`: spreadsheet-friendly rows with all three scores.
- `manual_review.json`: self-contained review queue.
- `report.md`: readable score and case tables.

Ctrl+C saves an interrupted state and any current interrupted case. Each file replacement is atomic; a hard process/OS crash between replacements can leave derived reports one case behind. `raw_results.json` is written first and is the recovery source. There is no automatic resume or parallel execution.

Original v1 files are preserved under `benchmarks/backups/v1`. Historical result folders are not rewritten. All 40 prompts and expected answers/tests are preserved; the four requested ambiguity fixes were already present and were verified during migration.

Regrade history without making model requests:

```powershell
python benchmarks\run_benchmarks.py --regrade benchmarks\results\20260912_170626_gemma-extraction-test\raw_results.json --name gemma-extraction-v2-review
```

Regrading writes a new run, retains original grades and source metadata, and uses current case policies. Older v1 results did not store prompts, so the review displays the current matching case prompt. Regrading cannot make an earlier ambiguous prompt unambiguous or recover truncated output. Code cases execute again unless `--skip-code-tests` is supplied.

Validation:

```powershell
python -m unittest discover -s benchmarks -p test_benchmarks.py -v
```

The tests use a mock gateway, verify checkpointing and interruption, and run curated code examples. They do not consume model inference.

## End-to-end execution audit (2026-09-12)

The initial live pilot exhausted the original 256/384 token budgets during reasoning. The gateway provider also concatenated reasoning output with final messages. Its message-type filter was restored; an additive reasoning_output_tokens response metric now preserves reasoning usage separately. Model routing, reasoning settings, authentication, and bind addresses are unchanged.

Use `--max-output-tokens 4096` for the audited comparison protocol. This is a total generation budget including reasoning, applied equally to both models without changing prompts or expected answers. Omitting it preserves legacy case budgets and CLI behavior. Runs record SHA-256 hashes of benchmark and gateway source files.

Two grading corrections were made before full runs: extract_005 explicitly normalizes boolean or enabled/disabled states only for authentication and cors (schema types remain strict); long_001 sends unmatched free-text root causes to review rather than claiming a paraphrase is necessarily wrong. No expected values or prompts changed. Review policy and full comparison are under `results/20260912_comparison`.
