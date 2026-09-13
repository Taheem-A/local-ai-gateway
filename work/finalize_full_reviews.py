from pathlib import Path
import sys,json,copy,csv,io
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from grading import outcome
from reporting import make_summary, atomic_write
ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'benchmarks/results'

def finalize(tier, reviews):
    pattern='*gemma-full-validated*' if tier=='balanced' else '*gptoss-full-validated*'
    run=sorted(RESULTS.glob(pattern))[-1]
    raw=json.loads((run/'raw_results.json').read_text(encoding='utf-8'))
    assert raw['metadata']['state']=='completed' and len(raw['results'])==40
    rows=copy.deepcopy(raw['results']); queue=[]
    for row in rows:
        g=row['grade']; review=reviews.get(row['id'])
        if review is not None:
            row['automatic_grade']=copy.deepcopy(g)
            row['review']=review
            row['grade']=dict(g,**outcome(review['semantic_correct'],review.get('format_correct',g['format_correct']),review.get('instruction_following',g['instruction_following'])))
            queue.append(dict(id=row['id'],prompt=row['prompt'],expected=row['expected'],response_text=row['response']['text'],grade=g,review=dict(review,reviewer='Codex in-task rubric review; no external grading API')))
        assert row['grade']['semantic_correct'] is not None, row['id']
    reviewed=make_summary(rows)
    reviewed['by_category']={cat:make_summary([r for r in rows if r['category']==cat]) for cat in sorted({r['category'] for r in rows})}
    reviewed['reviewed_cases']=len(queue)
    reviewed['models']=sorted({r['response']['model'] for r in rows})
    reviewed['budget_hits']=sum(r['response'].get('output_tokens',0)>=r['request']['max_output_tokens'] for r in rows)
    reviewed['empty_answers']=sum(not r['response'].get('text','').strip() for r in rows)
    reviewed['coding_cases']={'passed':sum(r['grade']['semantic_correct'] is True for r in rows if r['category']=='coding'),'total':sum(r['category']=='coding' for r in rows)}
    for name,data in [('manual_review.json',queue),('reviewed_results.json',dict(metadata=raw['metadata'],results=rows)),('reviewed_summary.json',reviewed)]:
        atomic_write(run/name,json.dumps(data,indent=2,ensure_ascii=False))
    fields=['id','category','model','automatic_semantic','reviewed_semantic','format','instructions','review_notes']
    buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader()
    for r in rows:
        writer.writerow(dict(id=r['id'],category=r['category'],model=r['response']['model'],automatic_semantic=r.get('automatic_grade',r['grade'])['semantic_correct'],reviewed_semantic=r['grade']['semantic_correct'],format=r['grade']['format_correct'],instructions=r['grade']['instruction_following'],review_notes=r.get('review',{}).get('notes','')))
    atomic_write(run/'reviewed_results.csv','\ufeff'+buffer.getvalue())
    return dict(run=run.name,automatic=make_summary(raw['results']),reviewed=reviewed,rows=rows)

if __name__=='__main__':
    reviews=json.loads((ROOT/'work/full_reviews.json').read_text(encoding='utf-8'))
    all_runs={tier:finalize(tier,reviews[tier]) for tier in ('balanced','deep')}
    p=RESULTS/'20260912_comparison'
    (p/'comparison_data.json').write_text(json.dumps(all_runs,indent=2),encoding='utf-8')
    for tier,data in all_runs.items():print(tier,data['run'],json.dumps(data['reviewed'],indent=2))
