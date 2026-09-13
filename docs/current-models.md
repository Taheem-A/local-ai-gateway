# Current model configuration

## Default production profile

- Profile: `default`
- Model: `openai/gpt-oss-20b`
- Reasoning: `medium`
- Basis: completed 40-case benchmark comparison.

## Deep profile

- Profile: `deep`
- Model: `openai/gpt-oss-20b`
- Reasoning: `medium` for now.
- Why medium: high reasoning has not been benchmarked yet. The API permits an explicit reasoning override so low/medium/high can be measured without changing application code.

## Historical balanced profile

- Profile: `balanced`
- Model: `google/gemma-4-12b-qat`
- Purpose: preserve the exact meaning of the original Gemma benchmark command. Do not silently remap it to GPT-OSS.

## Fast candidate

- Profile: `fast`
- Model: `google/gemma-4-12b-qat`
- Status: candidate/current mapping only; not a proven final fast-tier recommendation.

## Baseline benchmark

See [benchmarks/results/20260912_comparison/](../benchmarks/results/20260912_comparison/).
