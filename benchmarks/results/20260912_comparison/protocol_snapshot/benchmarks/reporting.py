"""Versioned reports; every snapshot is replaced atomically per file."""
import csv
import io
import json
import os
import statistics
import tempfile
from pathlib import Path

DIMENSIONS = ('semantic_correct', 'format_correct', 'instruction_following')
METRICS = ('input_tokens', 'output_tokens', 'reasoning_output_tokens', 'tokens_per_second',
           'time_to_first_token_seconds', 'model_load_time_seconds')


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def make_summary(results):
    scores = {}
    for dimension in DIMENSIONS:
        values = [r['grade'].get(dimension) for r in results if r['grade'].get(dimension) is not None]
        scores[dimension] = dict(passed=sum(v is True for v in values), evaluated=len(values),
            percent=round(100 * sum(v is True for v in values)/len(values), 1) if values else None)
    tests = [t for r in results for t in r['grade'].get('tests', [])]
    performance = {}
    for metric in ('wall_time_seconds',) + METRICS:
        values = [r.get(metric) if metric == 'wall_time_seconds' else r.get('response', {}).get(metric) for r in results]
        values = [v for v in values if type(v) in (int, float)]
        performance[metric] = dict(observed=len(values), mean=statistics.mean(values) if values else None,
                                  median=statistics.median(values) if values else None,
                                  total=sum(values) if values else None)
    return dict(total_cases=len(results), scores=scores,
        manual_review=sum(r['grade']['status'] == 'manual' for r in results),
        errors=sum(r['grade']['status'] == 'error' for r in results),
        code_tests=dict(passed=sum(t['passed'] for t in tests), evaluated=len(tests)), performance=performance)


def save_results(run_dir, metadata, results):
    summary = make_summary(results)
    summary['by_category'] = {cat: make_summary([r for r in results if r['category'] == cat])
                              for cat in sorted({r['category'] for r in results})}
    def write_json(name, value):
        atomic_write(run_dir / name, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))
    write_json('raw_results.json', dict(metadata=metadata, results=results))
    write_json('summary.json', dict(metadata=metadata, summary=summary))
    manual = [dict(id=r['id'], prompt=r.get('prompt'), expected=r.get('expected'),
                   response_text=r.get('response', {}).get('text'), grade=r['grade'],
                   review=dict(semantic_correct=None, notes='', reviewer=''))
              for r in results if r['grade']['status'] == 'manual']
    write_json('manual_review.json', manual)
    columns = ('id', 'category', 'difficulty', 'quality', 'model', 'status') + DIMENSIONS + ('wall_time_seconds',) + METRICS + ('response_text', 'error')
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for r in results:
        response = r.get('response', {})
        row = {k: r.get(k) for k in columns}
        row.update({k: response.get(k) for k in ('model',) + METRICS})
        row.update({k: r['grade'].get(k) for k in ('status',) + DIMENSIONS})
        row['response_text'] = response.get('text')
        writer.writerow(row)
    atomic_write(run_dir / 'results.csv', '\ufeff' + buffer.getvalue())
    lines = ['# Benchmark v2', '', f"Run state: {metadata.get('state')}; completed: {len(results)}/{metadata['case_count']}", '',
             '| Dimension | Passed / evaluated | Percent |', '|---|---:|---:|']
    for key, score in summary['scores'].items():
        lines.append(f"| {key} | {score['passed']} / {score['evaluated']} | {score['percent']} |")
    lines += ['', f"Manual review: {summary['manual_review']}; errors: {summary['errors']}",
              '', 'Manual cases and errors are excluded from dimensions with unknown scores.', '',
              '| Case | Semantic | Format | Instructions | Status |', '|---|---|---|---|---|']
    for r in results:
        g = r['grade']
        lines.append('| ' + ' | '.join(str(x) for x in [r['id']] + [g.get(k) for k in DIMENSIONS] + [g['status']]) + ' |')
    lines += ['', 'Full gateway timings and token statistics are in summary.json; prompts, grading policy, and original responses are in raw_results.json.', '']
    atomic_write(run_dir / 'report.md', '\n'.join(lines))
