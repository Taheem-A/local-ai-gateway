from pathlib import Path
import json,hashlib,csv
root=Path('benchmarks/results');comp=root/'20260912_comparison';data=json.loads((comp/'comparison_data.json').read_text(encoding='utf-8'))
b=json.loads((root/data['balanced']['run']/'raw_results.json').read_text(encoding='utf-8'));g=json.loads((root/data['deep']['run']/'raw_results.json').read_text(encoding='utf-8'))
assert b['metadata']['source_sha256']==g['metadata']['source_sha256']
assert len(b['results'])==len(g['results'])==40
for a,z in zip(b['results'],g['results']):
 assert a['id']==z['id'] and a['prompt']==z['prompt'] and a['expected']==z['expected']
 ar=dict(a['request']);zr=dict(z['request']);assert ar.pop('quality')=='balanced' and zr.pop('quality')=='deep';assert ar==zr and ar['max_output_tokens']==4096
for f,sha in b['metadata']['source_sha256'].items():assert hashlib.sha256(Path(f).read_bytes()).hexdigest()==sha,f
count=0
for pattern in ('*pilot-initial*','*pilot-corrected*','*pilot-validated*','*gemma-full-validated*','*gptoss-full-validated*'):
 p=next(root.glob(pattern));r=json.loads((p/'raw_results.json').read_text(encoding='utf-8'));count+=len(r['results']);assert r['metadata']['state']=='completed'
 for name in ('raw_results.json','summary.json','manual_review.json'):json.loads((p/name).read_text(encoding='utf-8'))
 assert len(list(csv.DictReader((p/'results.csv').open(encoding='utf-8-sig',newline=''))))==len(r['results'])
 assert (p/'report.md').is_file()
assert count==95
bad=next(r for r in b['results'] if r['id']=='summary_002')['response'];assert bad['output_tokens']==4096 and bad['reasoning_output_tokens']==4093 and bad['text']==''
for tier,x in data.items():
 assert x['reviewed']['scores']['semantic_correct']['evaluated']==40 and x['reviewed']['manual_review']==0
 assert x['reviewed']['code_tests']=={'passed':13,'evaluated':13}
 print(tier,x['reviewed']['scores'])
check={'identical_suite_and_request_parameters_except_quality':True,'source_hashes_match_both_runs_and_current_files':True,'preserved_live_requests':count,'all_required_artifacts_parse':True,'all_reviews_complete':True,'code_tests_passed_per_model':13}
(comp/'artifact_validation.json').write_text(json.dumps(check,indent=2),encoding='utf-8')
print('Final artifact validation passed')
