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
- never silently convert a model's factual error into the expected value during normalization;
- treat retrieved RAG content as untrusted data rather than instructions;
- never mix embedding models or vector dimensions inside one RAG collection.

Ruff is configured in the root `pyproject.toml` with a 100-character line-length target and checks syntax-critical pycodestyle rules, undefined/unused names, and import ordering. Narrow per-file import-order exceptions must be documented in `pyproject.toml` rather than silently disabling broader lint rules.

## Required checks

Before a release or merge to `master`:

```powershell
ruff check .
python -m compileall -q app benchmarks clients/python/taheem_ai scripts tests work
pytest -q
```

The GitHub Actions quality job runs the same checks on pushes and pull requests. Tests for RAG use temporary SQLite databases and deterministic fake embeddings; CI must not require a GPU or live LM Studio server.

## Commenting philosophy

Comments and docstrings are useful when they preserve information that would otherwise be rediscovered later. Examples in this project include:

- why `balanced` still maps to Gemma even though GPT-OSS is the production default;
- why `default` is low reasoning and `deep` is high reasoning;
- why the gateway's `format: time` contract differs from RFC 3339 time;
- why timezone-qualified times must not be normalized by stripping their suffix;
- why benchmark results are immutable evidence;
- why generated benchmark code executes only through the fixed curated harness;
- why SQLite dense retrieval is intentionally used before adding an ANN/vector service;
- why embedding-model changes require collection reindexing;
- why RAG source text and operational metrics have different privacy boundaries.

Avoid comments such as `# increment counter` immediately above `counter += 1`.

## Benchmark changes

Do not edit a committed historical result directory.

If only grading logic changes, regrade into a new run. If prompts/expected answers change, bump the benchmark policy version and rerun. Keep the old prompts available for historical interpretation.

The RAG retrieval corpus follows the same rule: changing a document, query, expected document ID, ranking metric, or runner behavior that affects comparability requires a benchmark-version change. Never alter a committed retrieval result merely because a newer embedding model performs differently.

## Configuration changes

Defaults that affect production model/capability behavior belong in both:

- `app/config.py` for code defaults;
- `.env.example` for deployment guidance.

Update `docs/current-models.md`, `docs/architecture.md`, and `docs/api.md` when generation routing or embedding configuration changes.

Changing `EMBEDDING_MODEL` or a task prefix changes the retrieval vector space. Existing collections must be reindexed. The gateway intentionally returns `RAG_INDEX_INCOMPATIBLE` rather than attempting an unsafe automatic migration.

## Data boundaries

`data/` is git-ignored. The databases have different purposes:

- `data/gateway.db` contains non-content operational metrics;
- `data/rag.db` contains source chunks, metadata, and embeddings by design.

Do not copy either database into the repository. Treat `rag.db` with the same privacy expectations as the documents it indexes.

## Pull-request release checklist

Before merging a feature branch into `master`:

1. confirm no secrets, local databases, indexed source material, or generated build metadata are tracked;
2. run lint, compile, and tests;
3. verify the final GitHub Actions run succeeds on the actual head commit;
4. update docs to match runtime defaults;
5. preserve benchmark evidence used for routing/retrieval decisions;
6. run any required live local-model benchmark that CI cannot reproduce;
7. ensure the PR description summarizes the final state, not an obsolete intermediate plan;
8. only then mark the PR ready and merge it.
