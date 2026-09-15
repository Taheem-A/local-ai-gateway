# GPT-OSS tool-calling production validation — 2026-09-15

This record freezes the live Stage 2 tool-calling validation that qualified the initial tool abstraction for production use in Local AI Gateway.

## Immutable source run

The original generated artifacts remain unchanged at:

`benchmarks/results/20260915_114556_gptoss-tool-calling-v1_8cca0d/`

Do not edit those files. If the suite, grader, provider behavior, or gateway implementation changes materially, create a new benchmark version and a new result directory instead.

## Configuration

- Suite version: `1`
- Suite SHA-256: `1784465e7782ca37aceaa87b89be255d8230845ec58e8a0df1cb891764588680`
- Model: `openai/gpt-oss-20b`
- Gateway profile: `default`
- Resolved reasoning: `low`
- Max output tokens: `2048`
- Cases: `8`

## Results

- Tool-selection accuracy: **100%**
- Argument accuracy: **100%**
- Risk-annotation accuracy: **100%**
- Synthesis-constraint accuracy: **100%**
- Full-case success: **100%**
- Request errors: **0**
- Mean request latency: **4.8203 s**
- Median request latency: **2.0042 s**

Every fixed case passed, including:

- choosing the correct tool among distractors;
- typed and enum argument extraction;
- `write` risk propagation;
- `required`, `auto`, and `none` tool-choice behavior;
- choosing not to call a tool when no tool was needed;
- post-tool synthesis;
- refusing an injected tool-result instruction that attempted to replace the real `21 °C` observation with `999 °C`.

## Latency interpretation

The first benchmark request took `24.8698 s`. The remaining seven requests took approximately `1.34–2.59 s` each and averaged about **1.99 s**.

The first-case delay is therefore treated as a cold model/load-path cost rather than representative warm tool-call latency. The immutable benchmark retains the measured all-request mean; consumers should use the median and per-case timings when estimating normal warmed operation.

## End-to-end SDK smoke test

A separate live smoke test registered a trusted local `calculate` Python handler with `risk="read"`. GPT-OSS requested:

- tool: `calculate`
- arguments: `a=17`, `b=23`, `operation="multiply"`

The gateway validated the request, the SDK registry authorized and executed the handler, the handler returned `391`, and the forced final synthesis answered that the product of 17 and 23 is 391.

The temporary smoke-test script was not part of the production source tree.

## Decision

Stage 2 is accepted with the following production boundary:

1. `/v1/tools/turn` is a stateless model/tool protocol primitive and **never executes caller application code**.
2. Application-owned registries hold the actual trusted callables and execution authority.
3. Requested arguments are validated at the gateway and again locally immediately before execution.
4. SDK execution defaults to `read` tools only; `write` and `destructive` risks require explicit opt-in.
5. Tool results are untrusted external data, not authorization or higher-priority instructions.
6. `run_tools_once()` allows at most one execution round and then forces a no-more-tools synthesis turn.
7. Recursive multi-step autonomy remains deferred to Stage 7 (bounded agents).

This benchmark validates the fixed Stage 2 suite and the implemented local execution path. It does not prove that arbitrary future tools, schemas, prompts, or side-effect policies are universally safe or perfectly selected by the model.
