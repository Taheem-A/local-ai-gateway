import json
import subprocess
import sys
import tempfile
import os
import uuid
from pathlib import Path

def clean(text: str) -> str:
    return (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )


# ---------------------------------------------------------
# Code benchmark execution
# ---------------------------------------------------------

def run_code_tests(
    code: str,
    tests: list[dict],
) -> dict:
    """
    Runs generated Python in a separate Python process.

    IMPORTANT:
    Python -I provides isolation from the user's Python
    environment, but this is NOT a true security sandbox.

    Only use this for the curated benchmark prompts.
    """

    code = clean(code)

    # Remove Markdown fences if the model ignored instructions.
    if code.startswith("```"):
        lines = code.splitlines()

        lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        code = "\n".join(lines)

    marker = '__RESULT_' + uuid.uuid4().hex + '__'
    harness = [
        "",
        "import json as _json",
        "_results = []",
    ]

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
        f"print({marker!r} + "
        "_json.dumps(_results, ensure_ascii=False))"
    )

    script = code + "\n" + "\n".join(harness)

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "candidate.py"

        path.write_text(
            script,
            encoding="utf-8",
        )

        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=temp_dir,
                env={k: v for k, v in os.environ.items() if k.upper() in
                     {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH'}},
                encoding='utf-8',
                errors='replace',
            )

        except subprocess.TimeoutExpired:
            return {
                "status": "fail",
                "passed": False,
                "reason": "Generated code timed out.",
            }

    result_line = next(
        (
            line[len(marker):]
            for line in process.stdout.splitlines()
            if line.startswith(marker)
        ),
        None,
    )

    if result_line is None or process.returncode != 0:
        return {
            "status": "fail",
            "passed": False,
            "reason": (
                "Code test harness failed. "
                f"stderr: {process.stderr.strip()}"
            ),
        }

    details = json.loads(result_line)

    passed = all(
        item["passed"]
        for item in details
    )

    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "tests": details,
    }


