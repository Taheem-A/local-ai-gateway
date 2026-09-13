# Current model configuration

## Default

- Model: `openai/gpt-oss-20b`
- Reasoning: `medium`
- Basis: completed 40-case benchmark comparison.

## Deep

- Model: `openai/gpt-oss-20b`
- Reasoning: `medium` for now.
- Why medium: high reasoning has not been benchmarked yet. The API permits an explicit reasoning override so low/medium/high can be measured without changing application code.

## Fast candidate

- Model: `google/gemma-4-12b-qat`
- Status: legacy/current fast mapping only; not a proven fast-tier recommendation.

## Compatibility

`balanced` remains accepted by the API and benchmark runner as an alias for `default`.

## Baseline benchmark

See [benchmarks/results/20260912_comparison/](../benchmarks/results/20260912_comparison/).
