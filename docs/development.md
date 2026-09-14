# Development

## Python conventions

The project targets Python 3.12.

Use these conventions for application, benchmark, SDK, and script code:

- four-space indentation;
- type annotations on public functions and non-obvious internal helpers;
- module docstrings on modules whose purpose is not obvious from the filename alone;
- class/function docstrings when the contract, safety boundary, or non-obvious behavior matters;
- comments for **why**, invariants, compatibility decisions, and security/reliability constraints — not comments that merely repeat the code;
- `snake_case` for functions/variables, `PascalCase` for classes, and uppercase constants;
- keep provider-specific behavior inside provider adapters rather than leaking raw model IDs into applications;
- prefer stable gateway error codes over making clients parse exception text;
- never log prompt/response content by default;
- never silently convert a model's factual error into the expected value during normalization.

Ruff is configured in the root `pyproject.toml` with a 100-character line-length target and checks syntax-critical pycodestyle rules, undefined/unused names, and import ordering.

## Required checks

Before a release or merge to `master`:

```powershell
ruff check .
python -m compileall -q app benchmarks clients/python/taheem_ai scripts tests work
pytest -q
```

The GitHub Actions quality job runs the same checks on pushes and pull requests.

## Commenting philosophy

Comments and docstrings are useful when they preserve information that would otherwise be rediscovered later. Examples in this project include:

- why `balanced` still maps to Gemma even though GPT-OSS is the production default;
- why `default` is low reasoning and `deep` is high reasoning;
- why the gateway's `format: time` contract differs from RFC 3339 time;
- why timezone-qualified times must not be normalized by stripping their suffix;
- why benchmark results are immutable evidence;
- why generated benchmark code executes only through the fixed curated harness.

Avoid comments such as `# increment counter` immediately above `counter += 1`.

## Benchmark changes

Do not edit a committed historical result directory.

If only grading logic changes, regrade into a new run. If prompts/expected answers change, bump the benchmark policy version and rerun. Keep the old prompts available for historical interpretation.

## Configuration changes

Defaults that affect production model routing belong in both:

- `app/config.py` for code defaults;
- `.env.example` for deployment guidance.

Update `docs/current-models.md`, `docs/architecture.md`, and `docs/api.md` when the public routing contract changes.

## Pull-request release checklist

Before merging a feature branch into `master`:

1. confirm no secrets or generated build metadata are tracked;
2. run lint, compile, and tests;
3. verify the final GitHub Actions run succeeds on the actual head commit;
4. update docs to match runtime defaults;
5. preserve benchmark evidence used for routing decisions;
6. ensure the PR description summarizes the final state, not an obsolete intermediate plan;
7. only then mark the PR ready and merge it.
