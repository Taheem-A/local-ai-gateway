"""Execute only the benchmark suite's curated generated-Python test cases."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


def clean(text: str) -> str:
    """Normalize line endings and surrounding whitespace in generated code."""

    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def run_code_tests(code: str, tests: list[dict[str, Any]]) -> dict[str, Any]:
    """Run curated Python checks in an isolated child process.

    Python's ``-I`` flag limits interaction with the user's normal Python
    environment, but this is not a security sandbox. Only the repository's fixed
    benchmark prompts should be executed through this helper.
    """

    code = clean(code)

    # A model may ignore the no-Markdown instruction. Strip exactly one outer
    # fence so semantic correctness can still be tested separately from format.
    if code.startswith("```"):
        lines = code.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)

    marker = "__RESULT_" + uuid.uuid4().hex + "__"
    harness = ["", "import json as _json", "_results = []"]

    for test in tests:
        expression = test["expression"]
        expected = test["expected"]
        harness += [
            "try:",
            f"    _actual = {expression}",
            f"    _expected = {expected!r}",
            "    _results.append({",
            f"        'expression': {expression!r},",
            "        'passed': _actual == _expected,",
            "        'actual': repr(_actual),",
            "        'expected': repr(_expected)",
            "    })",
            "except Exception as _e:",
            "    _results.append({",
            f"        'expression': {expression!r},",
            "        'passed': False,",
            "        'actual': None,",
            f"        'expected': {repr(repr(expected))},",
            "        'error': repr(_e)",
            "    })",
        ]

    harness.append(
        f"print({marker!r} + _json.dumps(_results, ensure_ascii=False))"
    )
    script = code + "\n" + "\n".join(harness)

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "candidate.py"
        path.write_text(script, encoding="utf-8")

        child_env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"}
        }
        try:
            process = subprocess.run(
                [sys.executable, "-I", str(path)],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=temp_dir,
                env=child_env,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "fail",
                "passed": False,
                "reason": "Generated code timed out.",
            }

    result_line = next(
        (
            line[len(marker) :]
            for line in process.stdout.splitlines()
            if line.startswith(marker)
        ),
        None,
    )

    if result_line is None or process.returncode != 0:
        return {
            "status": "fail",
            "passed": False,
            "reason": f"Code test harness failed. stderr: {process.stderr.strip()}",
        }

    details = json.loads(result_line)
    passed = all(item["passed"] for item in details)
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "tests": details,
    }
