"""Regression tests for benchmark loading, grading, checkpointing, and code execution."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

import run_benchmarks as runner
from grading import grade, normalize

CASES = {case["id"]: case for case in runner.load_cases()}


class GradingTests(unittest.TestCase):
    """Verify deterministic grading rules independently from model inference."""

    def test_all_objective_golden_answers(self):
        for case in CASES.values():
            expected = case["expected"]
            if "value" not in expected:
                continue
            text = (
                json.dumps(expected["value"])
                if "json" in expected["mode"]
                else str(expected["value"])
            )
            with self.subTest(case=case["id"]):
                result = grade(case, text)
                self.assertTrue(result["semantic_correct"])
                self.assertTrue(result["format_correct"])

    def test_normalization_and_separate_format(self):
        case = CASES["extract_001"]
        answer = dict(
            case["expected"]["value"],
            course="mat186",
            assignment="Problem Set #2",
            due_date="Sept 18 2026",
            due_time="11:59pm",
            timezone="ET",
        )
        result = grade(case, json.dumps(answer))
        self.assertTrue(result["semantic_correct"])
        self.assertFalse(result["format_correct"])
        self.assertTrue(result["instruction_following"])

        answer["due_date"] = "2026-09-19"
        answer["due_time"] = "23:59"
        result = grade(case, json.dumps(answer))
        self.assertFalse(result["semantic_correct"])
        self.assertTrue(result["format_correct"])

    def test_guardrails(self):
        for value in ("September sometime", "09/10/26", "2026-02-30"):
            with self.assertRaises(ValueError):
                normalize(value, "date")
        self.assertNotEqual(normalize("EST", "timezone"), normalize("EDT", "timezone"))
        self.assertNotEqual(normalize("EST", "timezone"), normalize("ET", "timezone"))
        for value in (True, "NaN", "Infinity", "1,2", "12 dollars"):
            with self.assertRaises(ValueError):
                normalize(value, "number")

    def test_numbers_booleans_and_aliases(self):
        case = CASES["extract_002"]
        answer = dict(case["expected"]["value"], subtotal="82.50")
        result = grade(case, json.dumps(answer))
        self.assertTrue(result["semantic_correct"])
        self.assertFalse(result["format_correct"])

        case = CASES["extract_005"]
        answer = dict(case["expected"]["value"], authentication=1)
        self.assertFalse(grade(case, json.dumps(answer))["semantic_correct"])

        case = CASES["extract_003"]
        answer = dict(case["expected"]["value"])
        answer["service_name"] = answer.pop("service")
        result = grade(case, json.dumps(answer))
        self.assertTrue(result["semantic_correct"])
        self.assertFalse(result["schema_correct"])

        case = CASES["long_002"]
        answer = copy.deepcopy(case["expected"]["value"])
        answer["Lab 2"]["time"] = "11:59 PM"
        result = grade(case, json.dumps(answer))
        self.assertTrue(result["semantic_correct"])
        self.assertFalse(result["instruction_following"])

    def test_json_wrappers_truncation_and_duplicates(self):
        case = CASES["extract_001"]
        text = json.dumps(case["expected"]["value"])
        for wrapped in (f"```json\n{text}\n```", f"Here is the answer:\n{text}"):
            result = grade(case, wrapped)
            self.assertTrue(result["semantic_correct"])
            self.assertFalse(result["instruction_following"])

        for invalid in (text[:-3], text + text, '{"a":1,"a":2}', '{"x":NaN}'):
            self.assertIsNone(grade(case, invalid)["semantic_correct"])

    def test_labels_and_unicode_equivalence(self):
        case = CASES["classify_001"]
        for value in ("The correct classification is assignment.", "`assignment`", "Assignment"):
            result = grade(case, value)
            self.assertTrue(result["semantic_correct"])
            self.assertFalse(result["format_correct"])

        result = grade(case, "exam")
        self.assertFalse(result["semantic_correct"])
        self.assertTrue(result["instruction_following"])

        for value in (
            "not assignment",
            "assignment or exam",
            "It could be an assignment but I am unsure.",
        ):
            self.assertIsNone(grade(case, value)["semantic_correct"])

        complexity = grade(CASES["reason_004"], "O(n²)")
        self.assertTrue(complexity["semantic_correct"])
        self.assertFalse(complexity["format_correct"])

    def test_numeric(self):
        case = CASES["reason_003"]
        result = grade(case, "The answer is 11.")
        self.assertTrue(result["semantic_correct"])
        self.assertFalse(result["format_correct"])

        result = grade(case, "12")
        self.assertFalse(result["semantic_correct"])
        self.assertTrue(result["format_correct"])

        for value in ("11 or 12", "11 + 2 = 13", "NaN", "Infinity"):
            self.assertIsNone(grade(case, value)["semantic_correct"])
        self.assertTrue(grade(CASES["reason_001"], "0.30001")["semantic_correct"])

    def test_enabled_state_and_free_text_review(self):
        case = CASES["extract_005"]
        answer = dict(case["expected"]["value"], authentication="enabled", cors="disabled")
        result = grade(case, json.dumps(answer))
        self.assertTrue(result["semantic_correct"])
        self.assertFalse(result["format_correct"])

        answer["cors"] = "enabled"
        self.assertFalse(grade(case, json.dumps(answer))["semantic_correct"])
        answer["cors"] = 0
        self.assertFalse(grade(case, json.dumps(answer))["semantic_correct"])

        case = CASES["long_001"]
        answer = dict(case["expected"]["value"], root_cause="A non-existent model was configured")
        self.assertIsNone(grade(case, json.dumps(answer))["semantic_correct"])
        answer["recovery_time"] = "09:01"
        self.assertFalse(grade(case, json.dumps(answer))["semantic_correct"])

    def test_summary(self):
        case = CASES["summary_004"]
        result = grade(case, "An unbulleted paragraph.")
        self.assertIsNone(result["semantic_correct"])
        self.assertFalse(result["format_correct"])
        self.assertFalse(grade(case, "")["format_correct"])
        self.assertTrue(grade(case, "- One point.\n- Another point.")["format_correct"])
        self.assertFalse(
            grade(CASES["summary_001"], "word " * 51)["instruction_following"]
        )
        self.assertTrue(
            grade(CASES["summary_002"], "One sentence. Another sentence.")[
                "instruction_following"
            ]
        )

    def test_key_order(self):
        case = CASES["instruction_005"]
        answer = dict(reversed(list(case["expected"]["value"].items())))
        result = grade(case, json.dumps(answer))
        self.assertTrue(result["semantic_correct"])
        self.assertTrue(result["format_correct"])
        self.assertFalse(result["instruction_following"])

    def test_text_dimensions(self):
        result = grade(CASES["instruction_003"], "Local Artificial Intelligence Gateway")
        self.assertTrue(result["semantic_correct"])
        self.assertFalse(result["format_correct"])

        result = grade(CASES["instruction_004"], "RED\nGREEN\nYELLOW")
        self.assertFalse(result["semantic_correct"])
        self.assertTrue(result["format_correct"])

    def test_code_cases(self):
        answers = {
            "coding_001": (
                "def clamp(value, minimum, maximum):\n"
                " return max(minimum, min(value, maximum))"
            ),
            "coding_002": "def dedupe_preserve_order(items):\n return list(dict.fromkeys(items))",
            "coding_003": "def largest(numbers):\n return max(numbers)",
            "coding_004": (
                "def flatten_dict(data, prefix=''):\n"
                " result = {}\n"
                " for k, v in data.items():\n"
                "  key = prefix + '.' + k if prefix else k\n"
                "  if isinstance(v, dict): result.update(flatten_dict(v, key))\n"
                "  else: result[key] = v\n"
                " return result"
            ),
        }
        for key, code in answers.items():
            with self.subTest(case=key):
                result = grade(CASES[key], code)
                self.assertTrue(result["semantic_correct"])
                self.assertTrue(result["format_correct"])
                self.assertEqual(len(result["tests"]), len(CASES[key]["expected"]["tests"]))

        code = answers["coding_001"]
        fenced = f"```python\n{code}\n```"
        self.assertFalse(grade(CASES["coding_001"], fenced)["format_correct"])
        self.assertTrue(grade(CASES["coding_001"], fenced)["semantic_correct"])
        self.assertFalse(
            grade(CASES["coding_001"], "def clamp(*args): return 0")["semantic_correct"]
        )
        self.assertFalse(
            grade(CASES["coding_001"], "this is invalid python")["semantic_correct"]
        )
        self.assertFalse(
            grade(CASES["coding_001"], "while True: pass")["semantic_correct"]
        )
        self.assertIsNone(grade(CASES["coding_001"], code, False)["semantic_correct"])

    def test_current_suite_v3_fixes_known_ambiguities(self):
        policy = runner.load_suite_policy()
        self.assertEqual(policy["version"], 3)
        self.assertEqual(len(CASES), 40)
        self.assertEqual(CASES["classify_001"]["expected"]["value"], "assignment")
        self.assertIn("not the grammatical form", CASES["classify_001"]["prompt"])
        self.assertIn("irrelevant = unrelated to course", CASES["classify_004"]["prompt"])
        self.assertIn("generic value", CASES["project_005"]["prompt"])
        self.assertEqual(CASES["project_008"]["expected"]["value"]["B"], "default")
        self.assertIn("default profile", CASES["long_003"]["prompt"])

    def test_frozen_base_case_files_remain_v2(self):
        for path in runner.BENCH_DIR.glob("cases_*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], 2)


class RunnerTests(unittest.TestCase):
    """Verify sequential requests and crash-safe checkpoint behavior."""

    def run_mock(self, interrupt: bool = False):
        with tempfile.TemporaryDirectory() as temp:
            events = []

            def request(req):
                if req.url.path == "/health":
                    return httpx.Response(200, json={"status": "ok"})

                body = json.loads(req.content)
                self.assertEqual(
                    set(body),
                    {"prompt", "quality", "temperature", "max_output_tokens"},
                )
                self.assertEqual(req.headers["X-Local-AI-Key"], "test-key")

                if events:
                    snapshot = json.loads(
                        next(Path(temp).glob("*/raw_results.json")).read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(len(snapshot["results"]), len(events))

                events.append(body)
                if len(events) == 2:
                    if interrupt:
                        raise KeyboardInterrupt()
                    return httpx.Response(502, json={"detail": "model load failed"})

                case = next(case for case in CASES.values() if case["prompt"] == body["prompt"])
                return httpx.Response(
                    200,
                    json={
                        "text": json.dumps(case["expected"]["value"]),
                        "model": "mock",
                        "quality": "default",
                        "tokens_per_second": 25,
                        "input_tokens": 10,
                        "output_tokens": 20,
                    },
                )

            client = httpx.Client(transport=httpx.MockTransport(request))
            argv = [
                "runner",
                "--quality",
                "default",
                "--category",
                "structured_extraction",
                "--name",
                "test",
            ]
            with (
                patch.object(runner, "RESULTS_DIR", Path(temp)),
                patch.object(runner.httpx, "Client", return_value=client),
                patch.object(sys, "argv", argv),
                patch.dict(os.environ, {"GATEWAY_API_KEY": "test-key"}),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = runner.main()

            folder = next(Path(temp).iterdir())
            self.assertEqual(
                {path.name for path in folder.iterdir()},
                {
                    "raw_results.json",
                    "summary.json",
                    "results.csv",
                    "manual_review.json",
                    "report.md",
                },
            )
            data = json.loads((folder / "raw_results.json").read_text(encoding="utf-8"))
            self.assertEqual(
                data["metadata"]["state"], "interrupted" if interrupt else "completed"
            )
            self.assertEqual(data["metadata"]["version"], 3)
            self.assertEqual(len(data["results"]), 2 if interrupt else 5)
            self.assertEqual(result, 130 if interrupt else 0)

            summary = json.loads(
                (folder / "summary.json").read_text(encoding="utf-8")
            )["summary"]
            self.assertEqual(summary["errors"], 1)
            expected_evaluated = 1 if interrupt else 4
            self.assertEqual(
                summary["scores"]["semantic_correct"]["evaluated"], expected_evaluated
            )

    def test_sequential_checkpoint_and_error(self):
        self.run_mock()

    def test_interrupt(self):
        self.run_mock(True)


if __name__ == "__main__":
    unittest.main()
