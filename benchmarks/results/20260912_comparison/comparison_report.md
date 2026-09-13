# Local AI Gateway benchmark comparison

Completed 2026-09-12 on the local Windows Legion. All candidate inference used the existing localhost gateway.

## Recommendation

Prefer the existing **quality=deep (openai/gpt-oss-20b, MXFP4, medium reasoning)** for the tested text workloads: extraction, summaries, small coding tasks, and reasoning. It gave better format compliance and completed this suite in about half Gemma's request time. Its slower token generation and longer cold load did not translate into slower completed answers, because it used much less reasoning. The results do not support reserving deep only for rare difficult questions.

Keep **quality=balanced (google/gemma-4-12b-qat, Q4_0, default reasoning on)** as an available alternative, especially when its shorter cold startup matters. This run does not establish a quality or warm-latency advantage for it. No routing mappings were changed. No fast model or alternate reasoning setting was benchmarked, so no fast-tier recommendation is made.

## Main results

| Measure | Balanced: Gemma | Deep: GPT-OSS |
|---|---:|---:|
| Reviewed semantic correctness | 38/40 (95.0%) | 39/40 (97.5%) |
| Canonical output/schema/format | 20/40 (50.0%) | 32/40 (80.0%) |
| Reviewed instruction following | 21/40 (52.5%) | 33/40 (82.5%) |
| Automatic semantics, before review | 32/35 (91.4%) | 32/34 (94.1%) |
| Automatic instruction following | 20/40 (50.0%) | 32/40 (80.0%) |
| Code cases / execution tests | 4/4; 13/13 | 4/4; 13/13 |
| Summary semantic passes | 3/4 | 4/4 |
| Summary rubric concepts covered | 15/18 | 18/18 |
| HTTP/model request errors | 0/40 | 0/40 |
| Empty final answers / token-budget hits | 1 / 1 | 0 / 0 |
| Automatic manual queue / reviewed cases | 5 / 8 | 6 / 9 |
| Reviews still pending | 0 | 0 |

Automatic semantic denominators exclude unknown/manual grades; reviewed semantics include all 40 cases, including empty answers. Canonical format means the existing benchmark representation, which is sometimes stricter than the prompt. Reviewed instruction following passes Gemma summary_004 because it has the requested four bullets; its introduction was not forbidden. It also differs from automatic scoring for deep extract_003: its bare JSON uses the field names in the prompt, which did not mandate the benchmark's shorter canonical keys. Semantic correctness in the instruction_following category measures answer content; it is distinct from the overall instruction dimension.

## Latency, throughput, and tokens

| Measure | Gemma | GPT-OSS |
|---|---:|---:|
| Mean request latency (s) | 14.373 | 6.895 |
| Median request latency (s) | 10.713 | 5.953 |
| Sum of request time (s) | 574.938 | 275.804 |
| Mean generated tokens/s | 50.51 | 43.68 |
| Median generated tokens/s | 50.26 | 44.00 |
| Mean first-token latency (s) | 0.130 | 0.404 |
| Median first-token latency (s) | 0.113 | 0.396 |
| Cold model load (s; one observation) | 6.248 | 11.034 |
| Input tokens | 5,041 | 6,458 |
| Output tokens, including reasoning | 27,364 | 10,582 |
| Reasoning output tokens | 25,375 | 8,887 |
| Combined input + output tokens | 32,405 | 17,040 |
| Output less reasoning tokens (derived) | 1,989 | 1,695 |

GPT-OSS used **52.0% less request time** across this suite. Request latency includes gateway/provider work and cold load on the first case; it excludes local grading and report writing. Sum of request time is not total elapsed task time. Both models started each full run unloaded. The initial diagnostic Gemma pilot also observed an 8.812-second load; the table uses the full-run load for both models. Load is from storage/OS cache state as found, not a controlled cold-disk benchmark.

First-token latency is the provider's first generated token, which can be reasoning; it is not time to the first final-answer token. Output tokens and tokens/sec include reasoning. Tokenizers differ, so counts are not a shared unit of semantic work. Values are observed for all 40 requests except load time (one each). No time-to-first-final-answer metric was available.

## Semantic correctness by category

| Category | Cases | Gemma | GPT-OSS | Gemma mean latency (s) | GPT-OSS mean latency (s) |
|---|---:|---:|---:|---:|---:|
| classification | 5 | 4/5 (80.0%) | 4/5 (80.0%) | 4.95 | 2.92 |
| coding | 4 | 4/4 (100.0%) | 4/4 (100.0%) | 27.53 | 5.37 |
| gateway_operations | 2 | 2/2 (100.0%) | 2/2 (100.0%) | 9.49 | 6.68 |
| instruction_following | 5 | 5/5 (100.0%) | 5/5 (100.0%) | 3.93 | 3.51 |
| itqaan_metadata | 2 | 2/2 (100.0%) | 2/2 (100.0%) | 9.81 | 7.28 |
| listening_data | 2 | 2/2 (100.0%) | 2/2 (100.0%) | 13.06 | 7.37 |
| long_context_analysis | 1 | 1/1 (100.0%) | 1/1 (100.0%) | 46.95 | 31.23 |
| long_context_reasoning | 1 | 1/1 (100.0%) | 1/1 (100.0%) | 10.99 | 8.50 |
| long_context_retrieval | 2 | 2/2 (100.0%) | 2/2 (100.0%) | 18.39 | 12.95 |
| reasoning | 5 | 5/5 (100.0%) | 5/5 (100.0%) | 8.80 | 5.38 |
| structured_extraction | 5 | 5/5 (100.0%) | 5/5 (100.0%) | 11.42 | 9.31 |
| summarization | 4 | 3/4 (75.0%) | 4/4 (100.0%) | 33.78 | 6.95 |
| university_tooling | 2 | 2/2 (100.0%) | 2/2 (100.0%) | 12.37 | 6.32 |

Per-category format and instruction scores are in each reviewed_summary.json and comparison_data.json.

## Failures, ambiguities, and review decisions

- **classify_004, both models:** returned announcement; expected irrelevant. The prompt calls the text a cafeteria notice but does not define academic relevance. Original expected answer and scored failure retained. Excluding this disputed case gives Gemma 38/39 (97.4%) and GPT-OSS 39/39 (100%); the relative conclusion is unchanged.
- **summary_002, Gemma:** consumed all 4,096 output tokens (4,093 reported reasoning tokens) and returned an empty final message after 89.216 seconds. This is a failed delivered answer, despite HTTP success. No expected answer or budget was adjusted after the full run.
- **long_001, both:** the prose root cause correctly describes a nonexistent model identifier. Reviewed semantic passes; Gemma still fails JSON-only formatting because of its fence.
- **long_002, Gemma:** all four deadlines are right, in combined date-time strings. Nested objects were not prescribed. Reviewed semantic pass; benchmark schema and Markdown-fence failures retained.
- **project_005, both:** chemistry lecture is an accurate specialization of lecture; no restricted event_type vocabulary was specified. Reviewed semantic passes.
- **reason_004, GPT-OSS:** O(n²) is mathematically correct but differs from the permitted literal O(n^2). Reviewed semantic pass, exact-format/instruction failure.
- **extract_003, GPT-OSS:** requested facts in bare JSON with literal prompt field names; semantic and reviewed instruction passes, canonical schema failure.
- Gemma repeatedly fences JSON. GPT-OSS also does so in several cases. Neither model achieved universal strict format compliance. Gemma summary_004 uses four bullets plus an introduction, failing the existing canonical bullet-only format check; reviewed explicit instruction compliance passes because an introduction is not forbidden. All its rubric concepts are covered.

Automatic grades remain untouched in raw_results.json, summary.json, results.csv and the original report section. Manual review records explain every adjudication in newly created runs. reviewed_results.json retains automatic_grade when changed; reviewed_summary.json and reviewed_results.csv carry the final scores. All eight summary reviews use the pre-existing concepts and constraints, not keyword-based semantic grading.

## Summary rubric review

| Model | Case | Concept coverage | Semantic pass | Mechanical format | Justification |
|---|---|---:|---|---|---|
| balanced | summary_001 | 5/5 | True | True | All five required concepts covered: v2.4, slowdown, database query, rollback, and redesign before redeployment. Accurate and within 50 words. |
| balanced | summary_002 | 0/3 | False | False | No final answer: all 4096 generated tokens were consumed before a message was delivered. Covers zero rubric concepts and fails the two-sentence requirement. This is a generation-budget failure, not a request error. |
| balanced | summary_003 | 4/4 | True | True | Covers all four concepts: local gateway abstraction, provider-independent requests, routing/model selection, and replacement without app changes. No material unsupported claim; 47 words. |
| balanced | summary_004 | 6/6 | True | False | All six incident facts and actions are covered accurately. Four bullets plus an introductory line fail the existing canonical bullet-only format check. The prompt only limits the number of bullets and does not forbid an introduction; reviewed instruction following therefore passes. |
| deep | summary_001 | 5/5 | True | True | All five concepts covered accurately, including full table scan, rollback time, and redesign before redeployment; 42 words. |
| deep | summary_002 | 3/3 | True | True | Precisely covers new Lab 3 deadline and time, all sections, and unchanged Lab 4 deadline; exactly two sentences and no invented extension. |
| deep | summary_003 | 4/4 | True | True | Covers current provider coupling, gateway abstraction, provider-independent requests, routing/model selection, and provider changes without app edits. No material unsupported claims; within 70 words. |
| deep | summary_004 | 6/6 | True | True | All six required concepts covered in four bullets. The 08:26-08:31 interval summarizes worker disablement and recovery correctly; no data loss and fix/tests before re-enabling are explicit. |

## Protocol and hardware

- Windows Legion model 83LU; NVIDIA RTX 5070 Ti Laptop GPU, 12,227 MiB reported VRAM; 33,752,997,888 bytes physical RAM; NVIDIA driver 616.92.
- LM Studio and gateway were already running on 127.0.0.1:1234 and 127.0.0.1:4812. Authenticated model inventory confirmed both exact model IDs and quantizations were installed. No download or model substitution was needed.
- Both full runs used all 40 case IDs in identical order, temperature 0.0, 16,384 context, and 4,096 total output tokens per request. Gemma reasoning was its LM Studio default on; GPT-OSS used the configured medium setting. This compares the configured tiers, not equal reasoning algorithms.
- Requests were strictly sequential; Gemma completed before GPT-OSS began. Models were unloaded between full runs. Generated code ran only for four curated Python cases using the pre-existing temporary-directory, python -I, five-second mechanism.
- Device-wide GPU memory snapshots during inference were 10,755 MiB for Gemma and 10,453 MiB for GPT-OSS. They include desktop/other allocations, are not peaks or model-only measurements, and do not establish RAM/offload costs. Both models ran successfully within the current setup.
- No OpenAI API or Codex inference was used as a candidate backend or grading API. Codex performed recorded rubric/adjudication review in this task. No service was exposed beyond localhost.
- This is one sequential run per model, plus Gemma pilots. It is a small, curated suite, not statistical evidence of broad superiority. The longer-context cases are short logs/documents and do not test the 16K context limit. Vision, real tool use, long-form coding, heavy concurrent load, and alternate reasoning settings were not benchmarked.

## Inspection, fixes, and validation

All 40 cases parse with unique IDs. reason_002 was independently enumerated and uniquely yields Monday=A, Tuesday=B, Wednesday=D, Thursday=C. project_005 and long_002 explicitly state 2026. long_004 defines alphabetical tie-breaking; its source values independently sum to 1,867,000 ms with eight completed listens. These four prompt fixes were already present.

The first live pilot reproduced all five incomplete outputs at the original 256/384 token caps. Inspection found that app/lmstudio.py had its message-type filter commented out and was returning reasoning as answer text. The filter was restored, and reasoning_output_tokens was added through provider, response schema, endpoint and benchmark reporting. No routing, reasoning setting, auth or bind-address changes were made. The gateway was restarted locally with the existing environment. Original app files were backed up under benchmarks/backups/pre_execution_20260912.

The runner gained optional --max-output-tokens and source SHA-256 records. Original CLI calls still work and retain the original per-case budgets when the override is omitted. After a corrected pilot exposed an enabled/disabled versus boolean mismatch, a narrow enabled_state rule was added only to extract_005 authentication/cors, keeping strict schema types. long_001 unmatched root-cause prose was routed to review. All 40 prompt texts, expected values and curated test expressions remained unchanged.

Validation passed 15 benchmark regression tests plus a provider-response regression with separate reasoning, message and tool-call items. The suite tests cover controlled normalization, wrong values, ambiguous prose, schema separation, unique IDs, code execution, sequential requests, checkpointing and interruption. The final artifact check confirms identical full-run requests except quality, all 95 live requests preserved, all required outputs, complete reviews, and matching frozen suite hashes.

## Runs and saved artifacts

Project report: C:\Projects\local-ai-gateway\benchmarks\results\20260912_comparison\comparison_report.md

All prior results remain untouched. New run folders:

| Run | Requests | Folder |
|---|---:|---|
| Initial Gemma diagnostic | 5 | `20260912_173833_420409_gemma-extraction-pilot-initial_ad77f4` |
| Gateway/budget correction pilot | 5 | `20260912_174013_835556_gemma-extraction-pilot-corrected_d92408` |
| Validated grading pilot | 5 | `20260912_174141_002517_gemma-extraction-pilot-validated_1fcec7` |
| Gemma full comparison | 40 | `20260912_174251_733938_gemma-full-validated_538f25` |
| GPT-OSS full comparison | 40 | `20260912_175248_495461_gptoss-full-validated_228236` |

Each run contains raw_results.json, summary.json, results.csv, manual_review.json and report.md. Both full runs additionally contain reviewed_results.json, reviewed_summary.json, reviewed_results.csv and reviewed_report.md. The comparison folder contains environment/runtime snapshots, execution_audit.json, the frozen review_policy.md, protocol_snapshot, comparison_data.json and this report.

Commands used for the final protocol:

```powershell
python benchmarks\run_benchmarks.py --quality balanced --category structured_extraction --max-output-tokens 4096 --name gemma-extraction-pilot-validated
python benchmarks\run_benchmarks.py --quality balanced --max-output-tokens 4096 --name gemma-full-validated
python benchmarks\run_benchmarks.py --quality deep --max-output-tokens 4096 --name gptoss-full-validated
```

## Remaining benchmark limitations

The cafeteria classification needs a future, predeclared relevance definition. Several extraction prompts leave key names, nested layout or value vocabularies unspecified while the canonical schema is strict; those differences required transparent review in this audit. Future suite revisions should declare required schema and label vocabulary up front, then be benchmarked as a new version. Do not compare the original tiny-budget runs as though they used this protocol. The standard CLI does not automatically apply manual reviews.

LM Studio response semantics and management endpoints were checked against its [chat API documentation](https://lmstudio.ai/docs/developer/rest/chat) and [unload documentation](https://lmstudio.ai/docs/developer/rest/unload). These document separate reasoning/message output items, reasoning usage, and optional load timing. All model-comparison claims above come from saved local measurements.
