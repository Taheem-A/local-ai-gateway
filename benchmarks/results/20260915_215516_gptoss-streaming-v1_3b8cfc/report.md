# Streaming benchmark

- Suite version: 1
- Suite SHA-256: `93d48e3947ca26c25f82696336c134f0696209461614da1363e5386445d8f12b`
- Model: `openai/gpt-oss-20b`
- Profile: `default`
- Reasoning: `low`
- Cases: 3
- Protocol accuracy: 100.00%
- Aggregate match: 100.00%
- Incremental delivery: 100.00%
- Request-ID consistency: 100.00%
- Full case success: 100.00%
- Request errors: 0
- Mean first-text latency: 4.9463s
- Median first-text latency: 0.7579s
- Mean total latency: 7.5837s
- Median total latency: 6.7957s
- Mean delta count: 131.33

| Case | Pass | Deltas | First text (s) | Total (s) |
|---|---:|---:|---:|---:|
| stream-short | yes | 4 | 13.519802900002105 | 13.6075 |
| stream-long | yes | 310 | 0.5612827000004472 | 6.7957 |
| stream-bangla | yes | 80 | 0.7579212999989977 | 2.3480 |
