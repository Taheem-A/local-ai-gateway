# Benchmark v2

Run state: completed; completed: 5/5

| Dimension | Passed / evaluated | Percent |
|---|---:|---:|
| semantic_correct | 4 / 5 | 80.0 |
| format_correct | 0 / 5 | 0.0 |
| instruction_following | 0 / 5 | 0.0 |

Manual review: 0; errors: 0

Manual cases and errors are excluded from dimensions with unknown scores.

| Case | Semantic | Format | Instructions | Status |
|---|---|---|---|---|
| extract_001 | True | False | False | pass_with_format_issue |
| extract_002 | True | False | False | pass_with_format_issue |
| extract_003 | True | False | False | pass_with_format_issue |
| extract_004 | True | False | False | pass_with_format_issue |
| extract_005 | False | False | False | fail |

Full gateway timings and token statistics are in summary.json; prompts, grading policy, and original responses are in raw_results.json.
