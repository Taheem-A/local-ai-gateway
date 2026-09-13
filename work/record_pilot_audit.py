from pathlib import Path
import json
p=Path('benchmarks/results/20260912_comparison')
notes={
 'initial_pilot':{'run':next(Path('benchmarks/results').glob('*pilot-initial*')).name,'findings':{k:'Generation reached original total token cap; only incomplete reasoning was returned. No complete final answer; semantic delivery fails on review, format and instructions fail. Gateway concatenated reasoning with messages.' for k in ['extract_001','extract_002','extract_003','extract_004','extract_005']}},
 'corrected_pilot':{'run':next(Path('benchmarks/results').glob('*pilot-corrected*')).name,'findings':{'extract_001':'Correct content, named-month date/12-hour time accepted semantically; Markdown fence fails JSON-only instruction.','extract_002':'Correct receipt values; Markdown fence fails JSON-only instruction.','extract_003':'Correct values under explicit field aliases; canonical schema differs and Markdown fence fails JSON-only instruction.','extract_004':'All Friday events correct; Markdown fence fails JSON-only instruction.','extract_005':'Correct final configuration. False negative arose from enabled/disabled strings versus booleans; prompt specifies keys but not types. Corrected with a field-specific enabled_state rule, with types still failing canonical schema.'}},
 'validated_pilot':{'run':next(Path('benchmarks/results').glob('*pilot-validated*')).name,'findings':{k:'Semantic PASS; format/instructions FAIL due to Markdown fence. Full answer inspected and compared to source.' for k in ['extract_001','extract_002','extract_003','extract_004','extract_005']}},
 'changes': ['Restored LM Studio output item type==message filter in app/lmstudio.py.', 'Added reasoning_output_tokens to provider and gateway response schema and reporting.', 'Added optional --max-output-tokens override; legacy CLI/default budgets preserved.', 'Added benchmark/gateway source SHA-256 metadata per run.', 'Added controlled enabled_state normalization only to extract_005 authentication/cors.', 'Added manual fallback for unmatched long_001 root_cause prose.', 'Added regression tests for enabled_state guardrails and free-text review; 15 benchmark tests and provider response regression pass.'],
 'unchanged': ['All 40 prompts and expected values/tests.', 'All four requested ambiguity fixes already present.', 'Model IDs, routing and reasoning defaults.', 'Localhost binding and credentials.', 'Existing result history.']}
(p/'execution_audit.json').write_text(json.dumps(notes,indent=2),encoding='utf-8')
for key in ('initial_pilot','corrected_pilot','validated_pilot'):
 run=Path('benchmarks/results')/notes[key]['run'];q=run/'manual_review.json';reviews=json.loads(q.read_text(encoding='utf-8'))
 existing={r['id']:r for r in reviews}
 raw=json.loads((run/'raw_results.json').read_text(encoding='utf-8'))
 for row in raw['results']:
  item=existing.get(row['id'],{'id':row['id'],'prompt':row['prompt'],'expected':row['expected'],'response_text':row['response'].get('text'),'grade':row['grade']})
  item['review']={'semantic_correct':key!='initial_pilot','notes':notes[key]['findings'][row['id']],'reviewer':'Codex in-task review; no grading API','format_correct':False,'instruction_following':False}
  existing[row['id']]=item
 q.write_text(json.dumps(list(existing.values()),indent=2),encoding='utf-8')
