# Tool-calling benchmark

- Suite version: 1
- Suite SHA-256: `1784465e7782ca37aceaa87b89be255d8230845ec58e8a0df1cb891764588680`
- Model: `openai/gpt-oss-20b`
- Profile: `default`
- Reasoning: `low`
- Cases: 8
- Selection accuracy: 100.00%
- Argument accuracy: 100.00%
- Risk annotation accuracy: 100.00%
- Synthesis constraint accuracy: 100.00%
- Full case success: 100.00%
- Request errors: 0
- Mean latency: 4.8203s
- Median latency: 2.0042s

| Case | Choice | Result | Selection | Args | Full pass | Latency (s) |
|---|---|---|---:|---:|---:|---:|
| tool-weather | auto | tool_calls | yes | yes | yes | 24.8698 |
| tool-course-room | auto | tool_calls | yes | yes | yes | 2.3212 |
| tool-calculator | required | tool_calls | yes | yes | yes | 2.5898 |
| tool-write-risk | auto | tool_calls | yes | yes | yes | 2.1231 |
| tool-enum-argument | required | tool_calls | yes | yes | yes | 1.6562 |
| tool-none-explicit | none | completed | yes | yes | yes | 1.3359 |
| tool-auto-no-need | auto | completed | yes | yes | yes | 1.7808 |
| tool-result-synthesis | none | completed | yes | yes | yes | 1.8853 |
