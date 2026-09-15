# BGE-M3 RAG retrieval validation — 2026-09-14

This directory records the production-validation decision for Stage 1 (Embeddings + RAG).

The immutable live benchmark artifacts are stored at:

`benchmarks/results/20260914_213509_bge-m3-rag-v1_dedb85/`

## Environment and configuration

- embedding model: `text-embedding-bge-m3`
- embedding dimensions: 1024
- retrieval top-k: 5
- benchmark suite version: 1
- suite SHA-256: `26dc2cc75c23f6b4f7ea168344638e83b8d3db1f07efb5bf8847da03e3de3189`
- corpus documents: 10
- indexed chunks: 10
- query cases: 10
- languages represented: English, Bengali, Arabic

## Result

| Metric | Result |
|---|---:|
| Recall@1 | 100.0% |
| Recall@3 | 100.0% |
| Recall@5 | 100.0% |
| Mean reciprocal rank | 1.0000 |
| Mean retrieval latency | 0.0467 s |
| Median retrieval latency | 0.0465 s |
| Total benchmark time | 2.106 s |

Every expected document ranked first for its query, including the Bengali and Arabic cases.

An additional live end-to-end smoke test on the same local gateway successfully exercised document indexing, semantic retrieval, GPT-OSS grounded answer generation, citation resolution back to the indexed source, and collection cleanup.

## Interpretation

This run validates the first production embedding configuration and the complete local retrieval path on the target machine. It does **not** establish that retrieval will remain perfect on large or difficult corpora: the validation corpus contains only ten documents and ten chunks. Future changes to the embedding model, chunking strategy, vector store, retrieval scoring, or benchmark corpus must be measured with a new immutable run rather than rewriting these artifacts.

## Decision

BGE-M3 is accepted as the Stage 1 production embedding model. The initial store remains SQLite with brute-force cosine retrieval until real corpus size or latency demonstrates a need for an ANN/vector database.
