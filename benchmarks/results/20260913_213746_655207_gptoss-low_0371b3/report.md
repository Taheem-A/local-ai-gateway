# Benchmark v2

Run state: completed; completed: 40/40

| Dimension | Passed / evaluated | Percent |
|---|---:|---:|
| semantic_correct | 30 / 33 | 90.9 |
| format_correct | 29 / 39 | 74.4 |
| instruction_following | 29 / 39 | 74.4 |

Manual review: 6; errors: 1

Manual cases and errors are excluded from dimensions with unknown scores.

| Case | Semantic | Format | Instructions | Status |
|---|---|---|---|---|
| extract_001 | True | False | False | pass_with_format_issue |
| extract_002 | True | False | False | pass_with_format_issue |
| extract_003 | True | False | False | pass_with_format_issue |
| extract_004 | True | False | False | pass_with_format_issue |
| extract_005 | True | True | True | pass |
| classify_001 | False | True | True | fail |
| classify_002 | False | True | True | fail |
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
| coding_004 | None | None | None | error |
| summary_001 | None | True | True | manual |
| summary_002 | None | True | True | manual |
| summary_003 | None | True | True | manual |
| summary_004 | None | True | True | manual |
| long_001 | None | True | True | manual |
| long_002 | True | False | False | pass_with_format_issue |
| long_003 | True | True | True | pass |
| long_004 | True | False | False | pass_with_format_issue |
| project_001 | True | True | True | pass |
| project_002 | True | True | True | pass |
| project_003 | True | False | False | pass_with_format_issue |
| project_004 | True | False | False | pass_with_format_issue |
| project_005 | True | True | True | pass |
| project_006 | True | False | False | pass_with_format_issue |
| project_007 | True | True | True | pass |
| project_008 | True | True | True | pass |

Full gateway timings and token statistics are in summary.json; prompts, grading policy, and original responses are in raw_results.json.
