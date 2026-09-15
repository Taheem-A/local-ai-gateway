# Current model configuration

## Production generation routing

| Profile | Model | Reasoning | Purpose |
|---|---|---|---|
| `fast` | `google/gemma-4-12b-qat` | none | Experimental candidate; not yet the final fast tier |
| `balanced` | `google/gemma-4-12b-qat` | none | Historical compatibility profile for old Gemma benchmarks |
| `default` | `openai/gpt-oss-20b` | `low` | Normal application requests |
| `deep` | `openai/gpt-oss-20b` | `high` | Tasks that justify substantially more reasoning time |

Applications should normally request `default` or `deep`, not raw model IDs. `medium` reasoning remains available through the explicit `reasoning` override when an application or experiment needs it.

## Embedding model

Embeddings are a separate capability from generation profiles.

Preferred configuration:

```dotenv
EMBEDDING_MODEL=text-embedding-bge-m3
EMBEDDING_QUERY_PREFIX=
EMBEDDING_DOCUMENT_PREFIX=
```

BGE-M3 is the Stage 1 production embedding model because the gateway is expected to index multilingual as well as English personal material, and it passed the live multilingual retrieval validation on the target machine. The raw LM Studio model key is an environment setting because locally downloaded revisions may expose a different key; verify it with `lms ls --embedding`.

Applications call `/v1/embeddings` or the RAG endpoints and never need to know that key. If the embedding model or dimension changes, existing RAG collections are considered incompatible and must be reindexed rather than mixing vector spaces.

If a different embedding family requires task prefixes, set `EMBEDDING_QUERY_PREFIX` and `EMBEDDING_DOCUMENT_PREFIX` in `.env`; do not bake those strings into applications.

## Why default uses low reasoning

The frozen 40-case September 2026 GPT-OSS comparison measured the same model and benchmark at low, medium, and high reasoning:

| Reasoning | Raw semantic | Format | Instructions | Mean latency | Median latency | Reasoning tokens | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| Low | 90.9% | 74.4% | 74.4% | 3.13 s | 2.30 s | 2,557 | 1 |
| Medium | 88.2% | 77.5% | 77.5% | 5.96 s | 5.66 s | 8,721 | 0 |
| High | 94.1% | 90.0% | 92.5% | 11.70 s | 8.49 s | 19,372 | 0 |

Manual review found the six subjective/manual cases semantically correct across all three runs. Several raw misses also came from benchmark-definition ambiguity rather than a clear model error. Low therefore offered the best everyday latency/quality trade-off, while high provided the strongest reliability at a much larger reasoning-token and latency cost.

The full immutable record is in [`benchmarks/history/2026-09-13-gptoss-reasoning/`](../benchmarks/history/2026-09-13-gptoss-reasoning/).

## Historical balanced profile

`balanced` intentionally remains Gemma 4 12B. It is not the production recommendation; it exists so old commands such as `--quality balanced` still mean what they meant when the original Gemma benchmark was recorded.

## Fast profile status

`fast` currently points to Gemma 4 12B as an experimental mapping. The GPT-OSS reasoning experiment did **not** establish a final fast tier. A future fast-model comparison must beat GPT-OSS low by enough latency to justify another model and the associated loading/routing complexity.

## RAG retrieval validation

BGE-M3 was validated live with `benchmarks/run_rag_benchmarks.py` using the fixed multilingual v1 suite. The committed run is `benchmarks/results/20260914_213509_bge-m3-rag-v1_dedb85/`:

| Metric | Result |
|---|---:|
| Embedding dimensions | 1024 |
| Recall@1 | 100.0% |
| Recall@3 | 100.0% |
| Recall@5 | 100.0% |
| Mean reciprocal rank | 1.0000 |
| Mean retrieval latency | 0.0467 s |
| Median retrieval latency | 0.0465 s |

All ten expected documents ranked first, including Bengali and Arabic cases. The validation record is frozen under [`benchmarks/history/2026-09-14-bge-m3-rag/`](../benchmarks/history/2026-09-14-bge-m3-rag/).

This establishes BGE-M3 as the initial production retriever and validates the local embedding/storage/search path. It does not imply that larger real-world corpora will maintain perfect retrieval; future model/chunking/store changes must be measured with new immutable runs.

## Older model comparison

The earlier Gemma-vs-GPT-OSS comparison remains under [`benchmarks/results/20260912_comparison/`](../benchmarks/results/20260912_comparison/).
