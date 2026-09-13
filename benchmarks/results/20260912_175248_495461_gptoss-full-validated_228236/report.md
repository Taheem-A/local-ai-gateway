# Benchmark v2

Run state: completed; completed: 40/40

| Dimension | Passed / evaluated | Percent |
|---|---:|---:|
| semantic_correct | 32 / 34 | 94.1 |
| format_correct | 32 / 40 | 80.0 |
| instruction_following | 32 / 40 | 80.0 |

Manual review: 6; errors: 0

Manual cases and errors are excluded from dimensions with unknown scores.

| Case | Semantic | Format | Instructions | Status |
|---|---|---|---|---|
| extract_001 | True | False | False | pass_with_format_issue |
| extract_002 | True | True | True | pass |
| extract_003 | True | False | False | pass_with_format_issue |
| extract_004 | True | False | False | pass_with_format_issue |
| extract_005 | True | True | True | pass |
| classify_001 | True | True | True | pass |
| classify_002 | True | True | True | pass |
| classify_003 | True | True | True | pass |
| classify_004 | False | True | True | fail |
| classify_005 | True | True | True | pass |
| instruction_001 | True | True | True | pass |
| instruction_002 | True | True | True | pass |
| instruction_003 | True | True | True | pass |
| instruction_004 | True | True | True | pass |
| instruction_005 | True | True | True | pass |
| reason_001 | True | True | True | pass |
| reason_002 | True | True | True | pass |
| reason_003 | True | True | True | pass |
| reason_004 | None | False | False | manual |
| reason_005 | True | True | True | pass |
| coding_001 | True | True | True | pass |
| coding_002 | True | True | True | pass |
| coding_003 | True | True | True | pass |
| coding_004 | True | True | True | pass |
| summary_001 | None | True | True | manual |
| summary_002 | None | True | True | manual |
| summary_003 | None | True | True | manual |
| summary_004 | None | True | True | manual |
| long_001 | None | True | True | manual |
| long_002 | True | True | True | pass |
| long_003 | True | True | True | pass |
| long_004 | True | True | True | pass |
| project_001 | True | True | True | pass |
| project_002 | True | False | False | pass_with_format_issue |
| project_003 | True | False | False | pass_with_format_issue |
| project_004 | True | True | True | pass |
| project_005 | False | True | True | fail |
| project_006 | True | False | False | pass_with_format_issue |
| project_007 | True | False | False | pass_with_format_issue |
| project_008 | True | True | True | pass |

Full gateway timings and token statistics are in summary.json; prompts, grading policy, and original responses are in raw_results.json.

## Completed review

The table above preserves automatic grading. Final reviewed scores and completed justifications are in reviewed_report.md, reviewed_summary.json, reviewed_results.csv, and manual_review.json.
