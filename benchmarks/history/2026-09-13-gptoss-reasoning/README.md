# GPT-OSS 20B reasoning benchmark — 2026-09-13

This directory is the historical record for the low/medium/high reasoning comparison that finalized the first production routing policy for the Local AI Gateway.

## Immutable evidence

The original generated artifacts remain unchanged in these result directories:

- `benchmarks/results/20260913_213746_655207_gptoss-low_0371b3/`
- `benchmarks/results/20260913_214111_111284_gptoss-medium_f22ff4/`
- `benchmarks/results/20260913_214528_069764_gptoss-high_5009ed/`

The branch head after those results were committed was `4abb4cb66aca89fb8f339b3c25ff9adcb784ab73`. Each run also contains SHA-256 hashes for the benchmark source files used at execution time. Historical result files should not be edited or regraded in place; corrections belong in a new benchmark version or a new regrade run.

## Controlled variable

All three runs used:

- model: `openai/gpt-oss-20b`
- quality profile: `default`
- the same 40 benchmark cases
- temperature: `0.0`
- maximum output budget: `4096` tokens per case
- sequential execution
- the same gateway/model stack

Only the explicit reasoning effort changed: `low`, `medium`, or `high`.

## Raw headline results

| Reasoning | Semantic | Format | Instructions | Mean latency | Median latency | Reasoning tokens | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Low | 90.9% | 74.4% | 74.4% | 3.13 s | 2.30 s | 2,557 | 1 |
| Medium | 88.2% | 77.5% | 77.5% | 5.96 s | 5.66 s | 8,721 | 0 |
| High | 94.1% | 90.0% | 92.5% | 11.70 s | 8.49 s | 19,372 | 0 |

The six manual-review cases in each run were semantically correct on inspection. Several raw-score misses also exposed benchmark-definition issues rather than model-quality issues, especially ambiguous classification labels and an underspecified `event_type` ontology.

## Routing decision

The production policy chosen from this experiment is:

- `default` -> GPT-OSS 20B, `low` reasoning
- `deep` -> GPT-OSS 20B, `high` reasoning
- `medium` remains available as an explicit override
- `balanced` remains the historical Gemma mapping for reproducibility
- `fast` remains experimental until a dedicated fast-tier comparison is performed

Low reasoning provided the strongest everyday latency/quality trade-off. High reasoning was the most reliable overall but consumed substantially more reasoning tokens and wall time, so it is reserved for tasks that justify the cost.

## Known benchmark-v2 limitations

These are preserved as evidence rather than rewritten retroactively:

1. `classify_001` mixes message form (an announcement) with referenced course-item type (an assignment).
2. `classify_004` does not define whether `irrelevant` means irrelevant to coursework or whether the message form itself may still be an announcement.
3. `project_005` expects the generic value `lecture` even though the prompt permits more specific values such as `Chemistry Lecture`.
4. `reason_004` treats `O(n²)` as a format/manual-review issue even though it is semantically identical to `O(n^2)`.
5. Low reasoning had one `502` during `coding_004`; the other low coding cases passed all executed tests, so this is recorded as an infrastructure error rather than silently treated as a model-quality failure.

The current benchmark suite addresses these issues in a new version while leaving these historical artifacts untouched.
