# RAG retrieval benchmark

- Suite version: 1
- Suite SHA-256: `26dc2cc75c23f6b4f7ea168344638e83b8d3db1f07efb5bf8847da03e3de3189`
- Embedding model: `text-embedding-bge-m3`
- Embedding dimensions: 1024
- Top-k: 5
- Cases: 10
- Recall@1: 100.00%
- Recall@3: 100.00%
- Recall@5: 100.00%
- MRR: 1.0000
- Mean latency: 0.0467s
- Median latency: 0.0465s

| Case | Expected document | Rank | Latency (s) |
|---|---|---:|---:|
| q-turnbuckle | structures-turnbuckle | 1 | 0.0504 |
| q-inverse | calculus-inverse | 1 | 0.0461 |
| q-dns | networks-dns | 1 | 0.0491 |
| q-context | python-context | 1 | 0.0496 |
| q-jupiter | space-jupiter | 1 | 0.0463 |
| q-mitochondria | biology-mitochondria | 1 | 0.0454 |
| q-bangla | bangla-capital | 1 | 0.0529 |
| q-arabic | arabic-qibla | 1 | 0.0419 |
| q-db-index | database-index | 1 | 0.0390 |
| q-git | git-branch | 1 | 0.0467 |
