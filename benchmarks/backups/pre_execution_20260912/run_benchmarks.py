from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from grading import grade
from reporting import save_results, make_summary

BENCH_DIR = Path(__file__).resolve().parent
ROOT = BENCH_DIR.parent
RESULTS_DIR = BENCH_DIR / 'results'


def load_env(path):
    if path.exists():
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))


def load_cases():
    cases, seen = [], set()
    for path in sorted(BENCH_DIR.glob('cases_*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        for case in data['cases']:
            if case['id'] in seen:
                raise ValueError(f"Duplicate benchmark ID: {case['id']}")
            seen.add(case['id'])
            cases.append(dict(case, _suite=data.get('suite', path.stem), _source=path.name,
                              _defaults=data.get('defaults', {})))
    if not cases:
        raise ValueError('No benchmark cases found')
    return cases


def now():
    return datetime.now().astimezone().isoformat()


def error_grade(reason):
    return dict(version=2, status='error', passed=None, semantic_correct=None,
                format_correct=None, instruction_following=None, reason=reason)


def main():
    parser = argparse.ArgumentParser(description='Sequential benchmark v2 with independent grading dimensions.')
    parser.add_argument('--quality', choices=['fast', 'balanced', 'deep'])
    parser.add_argument('--name')
    parser.add_argument('--category')
    parser.add_argument('--skip-code-tests', action='store_true')
    parser.add_argument('--regrade', type=Path, help='Regrade a saved raw/partial_results.json without model requests; writes a new run.')
    args = parser.parse_args()
    cases = load_cases()
    if args.category:
        cases = [c for c in cases if c['category'] == args.category]
    if not cases:
        parser.error('No cases match this category')
    label = re.sub(r'[^A-Za-z0-9._-]+', '_', args.name or args.quality or 'benchmark')
    run_dir = RESULTS_DIR / f"{datetime.now():%Y%m%d_%H%M%S_%f}_{label}_{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    metadata = dict(version=2, started_at=now(), forced_quality=args.quality, name=args.name,
                    case_count=len(cases), state='running', execute_code=not args.skip_code_tests)
    results: list[dict[str, Any]] = []
    if args.regrade:
        previous = json.loads(args.regrade.read_text(encoding='utf-8'))
        lookup = {c['id']: c for c in cases}
        selected = [r for r in previous['results'] if r['id'] in lookup]
        metadata.update(source_run=str(args.regrade.resolve()), source_metadata=previous.get('metadata'),
                        case_count=len(selected), historical_prompts_unchanged=True)
        for old in selected:
            case = lookup[old['id']]
            row = dict(old, original_grade=old['grade'], prompt=old.get('prompt', case['prompt']),
                       expected=case['expected'])
            row['grade'] = (error_grade(old.get('error') or 'Original request failed') if old['grade']['status'] == 'error'
                            else grade(case, old.get('response', {}).get('text', ''), not args.skip_code_tests))
            results.append(row)
            save_results(run_dir, metadata, results)
        metadata['state'] = 'completed'
        metadata['finished_at'] = now()
        save_results(run_dir, metadata, results)
        print(f'Regraded {len(results)} cases. Original run preserved.\nResults: {run_dir}')
        return 0
    load_env(ROOT / '.env')
    api_key = os.getenv('GATEWAY_API_KEY') or os.getenv('LOCAL_AI_GATEWAY_KEY')
    if not api_key:
        print('GATEWAY_API_KEY was not found in .env.', file=sys.stderr)
        return 2
    gateway = os.getenv('LOCAL_AI_GATEWAY_URL', 'http://127.0.0.1:4812').rstrip('/')
    save_results(run_dir, metadata, results)
    exit_code = 0
    try:
        with httpx.Client(timeout=300) as client:
            client.get(f'{gateway}/health').raise_for_status()
            for number, case in enumerate(cases, 1):
                defaults = case['_defaults']
                quality = args.quality or case.get('quality') or defaults.get('quality', 'balanced')
                body = dict(prompt=case['prompt'], quality=quality,
                            temperature=case.get('temperature', defaults.get('temperature', 0.0)),
                            max_output_tokens=case.get('max_output_tokens', 2048))
                if case.get('system'):
                    body['system'] = case['system']
                row: dict[str, Any] = dict(id=case['id'], suite=case['_suite'], source_file=case['_source'],
                           category=case['category'], difficulty=case['difficulty'], quality=quality,
                           prompt=case['prompt'], expected=case['expected'], request=body,
                           response={}, grade={}, error=None, wall_time_seconds=None)
                print(f"[{number:02d}/{len(cases):02d}] {case['id']} ({quality})", end=' ... ', flush=True)
                start = time.perf_counter()
                try:
                    response = client.post(f'{gateway}/v1/generate', headers={'X-Local-AI-Key': api_key}, json=body)
                    row['wall_time_seconds'] = round(time.perf_counter() - start, 3)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict) or not isinstance(data.get('text'), str):
                        raise ValueError('Gateway response must contain a string text field')
                    row['response'] = data
                    row['grade'] = grade(case, data['text'], not args.skip_code_tests)
                except KeyboardInterrupt:
                    row['error'] = 'Interrupted during case'
                    row['grade'] = error_grade(row['error'])
                    raise
                except Exception as error:
                    row['error'] = str(error)
                    row['grade'] = error_grade(row['error'])
                finally:
                    if row['wall_time_seconds'] is None:
                        row['wall_time_seconds'] = round(time.perf_counter() - start, 3)
                    results.append(row)
                    save_results(run_dir, metadata, results)
                print(str(row['grade'].get('status', '')).upper())
        metadata['state'] = 'completed'
    except KeyboardInterrupt:
        metadata['state'] = 'interrupted'
        exit_code = 130
    except Exception as error:
        metadata.update(state='error', error=str(error))
        print(f'Benchmark stopped: {error}', file=sys.stderr)
        exit_code = 3
    finally:
        metadata['finished_at'] = now()
        save_results(run_dir, metadata, results)
    summary: dict[str, Any] = make_summary(results)
    for key, score in summary['scores'].items():
        print(f"{key}: {score['passed']}/{score['evaluated']} ({score['percent']}%)")
    print(f'Results: {run_dir}')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
