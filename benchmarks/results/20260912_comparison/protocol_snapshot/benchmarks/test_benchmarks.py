import contextlib
import copy
import io
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
import run_benchmarks as runner
from grading import grade, normalize
from reporting import make_summary, save_results

CASES = {c['id']: c for c in runner.load_cases()}


class GradingTests(unittest.TestCase):
    def test_all_objective_golden_answers(self):
        for c in CASES.values():
            e = c['expected']
            if 'value' not in e:
                continue
            text = json.dumps(e['value']) if 'json' in e['mode'] else str(e['value'])
            with self.subTest(case=c['id']):
                self.assertTrue(grade(c, text)['semantic_correct'])
                self.assertTrue(grade(c, text)['format_correct'])

    def test_normalization_and_separate_format(self):
        c = CASES['extract_001']
        answer = dict(c['expected']['value'], course='mat186', assignment='Problem Set #2',
                      due_date='Sept 18 2026', due_time='11:59pm', timezone='ET')
        g = grade(c, json.dumps(answer))
        self.assertTrue(g['semantic_correct'])
        self.assertFalse(g['format_correct'])
        self.assertTrue(g['instruction_following'])  # Prompt doesn't require ISO.
        answer['due_date'] = '2026-09-19'
        answer['due_time'] = '23:59'
        g = grade(c, json.dumps(answer))
        self.assertFalse(g['semantic_correct'])
        self.assertTrue(g['format_correct'])

    def test_guardrails(self):
        for value in ('September sometime', '09/10/26', '2026-02-30'):
            with self.assertRaises(ValueError):
                normalize(value, 'date')
        self.assertNotEqual(normalize('EST', 'timezone'), normalize('EDT', 'timezone'))
        self.assertNotEqual(normalize('EST', 'timezone'), normalize('ET', 'timezone'))
        for value in (True, 'NaN', 'Infinity', '1,2', '12 dollars'):
            with self.assertRaises(ValueError):
                normalize(value, 'number')

    def test_numbers_booleans_nested_aliases(self):
        c = CASES['extract_002']
        a = dict(c['expected']['value'], subtotal='82.50')
        g = grade(c, json.dumps(a))
        self.assertTrue(g['semantic_correct'])
        self.assertFalse(g['format_correct'])
        c = CASES['extract_005']
        a = dict(c['expected']['value'], authentication=1)
        self.assertFalse(grade(c, json.dumps(a))['semantic_correct'])
        c = CASES['extract_003']
        a = dict(c['expected']['value'])
        a['service_name'] = a.pop('service')
        self.assertTrue(grade(c, json.dumps(a))['semantic_correct'])
        self.assertFalse(grade(c, json.dumps(a))['schema_correct'])
        c = CASES['long_002']
        a = copy.deepcopy(c['expected']['value'])
        a['Lab 2']['time'] = '11:59 PM'
        g = grade(c, json.dumps(a))
        self.assertTrue(g['semantic_correct'])
        self.assertFalse(g['instruction_following'])

    def test_json_wrappers_truncation_and_duplicates(self):
        c = CASES['extract_001']
        text = json.dumps(c['expected']['value'])
        for wrapped in ('```json\n' + text + '\n```', 'Here is the answer:\n' + text):
            g = grade(c, wrapped)
            self.assertTrue(g['semantic_correct'])
            self.assertFalse(g['instruction_following'])
        for invalid in (text[:-3], text + text, '{"a":1,"a":2}', '{"x":NaN}'):
            self.assertIsNone(grade(c, invalid)['semantic_correct'])

    def test_labels(self):
        c = CASES['classify_001']
        for value in ('The correct classification is assignment.', '`assignment`', 'Assignment'):
            g = grade(c, value)
            self.assertTrue(g['semantic_correct'])
            self.assertFalse(g['format_correct'])
        g = grade(c, 'exam')
        self.assertFalse(g['semantic_correct'])
        self.assertTrue(g['instruction_following'])
        for value in ('not assignment', 'assignment or exam', 'It could be an assignment but I am unsure.'):
            self.assertIsNone(grade(c, value)['semantic_correct'])

    def test_numeric(self):
        c = CASES['reason_003']
        g = grade(c, 'The answer is 11.')
        self.assertTrue(g['semantic_correct'])
        self.assertFalse(g['format_correct'])
        g = grade(c, '12')
        self.assertFalse(g['semantic_correct'])
        self.assertTrue(g['format_correct'])
        for value in ('11 or 12', '11 + 2 = 13', 'NaN', 'Infinity'):
            self.assertIsNone(grade(c, value)['semantic_correct'])
        self.assertTrue(grade(CASES['reason_001'], '0.30001')['semantic_correct'])

    def test_enabled_state_and_free_text_review(self):
        c = CASES['extract_005']
        a = dict(c['expected']['value'], authentication='enabled', cors='disabled')
        g = grade(c, json.dumps(a))
        self.assertTrue(g['semantic_correct'])
        self.assertFalse(g['format_correct'])
        a['cors'] = 'enabled'
        self.assertFalse(grade(c, json.dumps(a))['semantic_correct'])
        a['cors'] = 0
        self.assertFalse(grade(c, json.dumps(a))['semantic_correct'])
        c = CASES['long_001']
        a = dict(c['expected']['value'], root_cause='A non-existent model was configured')
        self.assertIsNone(grade(c, json.dumps(a))['semantic_correct'])
        a['recovery_time'] = '09:01'
        self.assertFalse(grade(c, json.dumps(a))['semantic_correct'])

    def test_summary(self):
        c = CASES['summary_004']
        g = grade(c, 'An unbulleted paragraph.')
        self.assertIsNone(g['semantic_correct'])
        self.assertFalse(g['format_correct'])
        self.assertFalse(grade(c, '')['format_correct'])
        self.assertTrue(grade(c, '- One point.\n- Another point.')['format_correct'])
        self.assertFalse(grade(CASES['summary_001'], 'word ' * 51)['instruction_following'])
        self.assertTrue(grade(CASES['summary_002'], 'One sentence. Another sentence.')['instruction_following'])

    def test_key_order(self):
        c = CASES['instruction_005']
        a = dict(reversed(list(c['expected']['value'].items())))
        g = grade(c, json.dumps(a))
        self.assertTrue(g['semantic_correct'])
        self.assertTrue(g['format_correct'])
        self.assertFalse(g['instruction_following'])

    def test_text_dimensions(self):
        g = grade(CASES['instruction_003'], 'Local Artificial Intelligence Gateway')
        self.assertTrue(g['semantic_correct'])
        self.assertFalse(g['format_correct'])
        g = grade(CASES['instruction_004'], 'RED\nGREEN\nYELLOW')
        self.assertFalse(g['semantic_correct'])
        self.assertTrue(g['format_correct'])

    def test_code_cases(self):
        answers = {
            'coding_001': 'def clamp(value, minimum, maximum):\n return max(minimum, min(value, maximum))',
            'coding_002': 'def dedupe_preserve_order(items):\n return list(dict.fromkeys(items))',
            'coding_003': 'def largest(numbers):\n return max(numbers)',
            'coding_004': "def flatten_dict(data, prefix=''):\n result = {}\n for k, v in data.items():\n  key = prefix + '.' + k if prefix else k\n  if isinstance(v, dict): result.update(flatten_dict(v, key))\n  else: result[key] = v\n return result",
        }
        for key, code in answers.items():
            with self.subTest(case=key):
                g = grade(CASES[key], code)
                self.assertTrue(g['semantic_correct'])
                self.assertTrue(g['format_correct'])
                self.assertEqual(len(g['tests']), len(CASES[key]['expected']['tests']))
        code = answers['coding_001']
        self.assertFalse(grade(CASES['coding_001'], '```python\n' + code + '\n```')['format_correct'])
        self.assertTrue(grade(CASES['coding_001'], '```python\n' + code + '\n```')['semantic_correct'])
        self.assertFalse(grade(CASES['coding_001'], 'def clamp(*args): return 0')['semantic_correct'])
        self.assertFalse(grade(CASES['coding_001'], 'this is invalid python')['semantic_correct'])
        self.assertFalse(grade(CASES['coding_001'], 'while True: pass')['semantic_correct'])
        self.assertIsNone(grade(CASES['coding_001'], code, False)['semantic_correct'])

    def test_cases_preserved(self):
        self.assertEqual(len(CASES), 40)
        for path in (runner.BENCH_DIR / 'backups/v1').glob('cases_*.json'):
            old = json.loads(path.read_text(encoding='utf-8'))
            for c in old['cases']:
                self.assertEqual(c['prompt'], CASES[c['id']]['prompt'])
                for key in ('value', 'tests'):
                    self.assertEqual(c['expected'].get(key), CASES[c['id']]['expected'].get(key))
        valid = [p for p in itertools.permutations('ABCD') if p[3]=='C' and p.index('B')==p.index('A')+1 and p.index('D')>p.index('B')]
        self.assertEqual(valid, [('A','B','D','C')])


class RunnerTests(unittest.TestCase):
    def run_mock(self, interrupt=False):
        with tempfile.TemporaryDirectory() as temp:
            events = []
            def request(req):
                if req.url.path == '/health':
                    return httpx.Response(200, json={'status':'ok'})
                body = json.loads(req.content)
                self.assertEqual(set(body), {'prompt','quality','temperature','max_output_tokens'})
                self.assertEqual(req.headers['X-Local-AI-Key'], 'test-key')
                if events:
                    snapshot = json.loads(next(Path(temp).glob('*/raw_results.json')).read_text(encoding='utf-8'))
                    self.assertEqual(len(snapshot['results']), len(events))
                events.append(body)
                if len(events) == 2:
                    if interrupt:
                        raise KeyboardInterrupt()
                    return httpx.Response(502, json={'detail':'model load failed'})
                c = next(c for c in CASES.values() if c['prompt'] == body['prompt'])
                return httpx.Response(200, json={'text': json.dumps(c['expected']['value']), 'model':'mock',
                    'quality':'balanced', 'tokens_per_second': 25, 'input_tokens':10, 'output_tokens':20})
            client = httpx.Client(transport=httpx.MockTransport(request))
            with patch.object(runner, 'RESULTS_DIR', Path(temp)), patch.object(runner.httpx, 'Client', return_value=client), \
                 patch.object(sys, 'argv', ['runner', '--quality','balanced','--category','structured_extraction','--name','test']), \
                 patch.dict(os.environ, {'GATEWAY_API_KEY':'test-key'}), contextlib.redirect_stdout(io.StringIO()):
                result = runner.main()
            folder = next(Path(temp).iterdir())
            self.assertEqual({p.name for p in folder.iterdir()}, {'raw_results.json','summary.json','results.csv','manual_review.json','report.md'})
            data = json.loads((folder/'raw_results.json').read_text(encoding='utf-8'))
            self.assertEqual(data['metadata']['state'], 'interrupted' if interrupt else 'completed')
            self.assertEqual(len(data['results']), 2 if interrupt else 5)
            self.assertEqual(result, 130 if interrupt else 0)
            summary = json.loads((folder/'summary.json').read_text(encoding='utf-8'))['summary']
            self.assertEqual(summary['errors'], 1)
            self.assertEqual(summary['scores']['semantic_correct']['evaluated'], 1 if interrupt else 4)

    def test_sequential_checkpoint_and_error(self):
        self.run_mock()

    def test_interrupt(self):
        self.run_mock(True)


if __name__ == '__main__':
    unittest.main()
