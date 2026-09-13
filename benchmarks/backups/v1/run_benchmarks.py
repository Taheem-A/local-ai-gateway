from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx


BENCH_DIR = Path(__file__).resolve().parent
ROOT = BENCH_DIR.parent
RESULTS_DIR = BENCH_DIR / "results"


# ---------------------------------------------------------
# Environment
# ---------------------------------------------------------

def load_env(path: Path) -> None:
    """
    Loads simple KEY=value pairs from the project's .env file.

    This means the benchmark runner can automatically use
    GATEWAY_API_KEY without you pasting the key into commands.
    """
    if not path.exists():
        return

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        key = key.strip()
        value = value.strip().strip('"').strip("'")

        os.environ.setdefault(key, value)


# ---------------------------------------------------------
# Benchmark loading
# ---------------------------------------------------------

def load_cases() -> list[dict]:
    """
    Loads every cases_*.json file in benchmarks/.
    """

    cases = []
    seen = set()

    for path in sorted(BENCH_DIR.glob("cases_*.json")):
        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        defaults = data.get("defaults", {})

        for case in data["cases"]:
            case_id = case["id"]

            if case_id in seen:
                raise ValueError(
                    f"Duplicate benchmark ID: {case_id}"
                )

            seen.add(case_id)

            cases.append(
                {
                    **case,
                    "_suite": data.get(
                        "suite",
                        path.stem,
                    ),
                    "_source": path.name,
                    "_defaults": defaults,
                }
            )

    if not cases:
        raise RuntimeError(
            "No cases_*.json benchmark files found."
        )

    return cases


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
        "print('__RESULT__' + "
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
            )

        except subprocess.TimeoutExpired:
            return {
                "status": "fail",
                "passed": False,
                "reason": "Generated code timed out.",
            }

    marker = "__RESULT__"

    result_line = next(
        (
            line[len(marker):]
            for line in process.stdout.splitlines()
            if line.startswith(marker)
        ),
        None,
    )

    if result_line is None:
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


# ---------------------------------------------------------
# Grading
# ---------------------------------------------------------

def grade(
    case: dict,
    text: str,
    execute_code: bool,
) -> dict:

    expected = case["expected"]
    mode = expected["mode"]

    # -----------------------------
    # Exact JSON
    # -----------------------------

    if mode == "exact_json":
        try:
            actual = json.loads(
                text.strip()
            )

        except json.JSONDecodeError as error:
            return {
                "status": "fail",
                "passed": False,
                "reason": (
                    f"Invalid JSON: {error}"
                ),
            }

        passed = (
            actual
            == expected["value"]
        )

        return {
            "status": (
                "pass"
                if passed
                else "fail"
            ),
            "passed": passed,
            "actual": actual,
            "expected": expected["value"],
        }

    # -----------------------------
    # Exact text
    # -----------------------------

    if mode == "exact_text":
        actual = clean(text)
        wanted = clean(
            str(expected["value"])
        )

        passed = (
            actual == wanted
        )

        return {
            "status": (
                "pass"
                if passed
                else "fail"
            ),
            "passed": passed,
            "actual": actual,
            "expected": wanted,
        }

    # -----------------------------
    # Numeric
    # -----------------------------

    if mode == "numeric":
        try:
            actual = float(
                text.strip()
            )

        except ValueError:
            return {
                "status": "fail",
                "passed": False,
                "reason": (
                    "Response was not "
                    "a bare numeric value."
                ),
            }

        wanted = float(
            expected["value"]
        )

        tolerance = float(
            expected.get(
                "tolerance",
                0,
            )
        )

        passed = (
            abs(actual - wanted)
            <= tolerance
        )

        return {
            "status": (
                "pass"
                if passed
                else "fail"
            ),
            "passed": passed,
            "actual": actual,
            "expected": wanted,
            "tolerance": tolerance,
        }

    # -----------------------------
    # Generated Python
    # -----------------------------

    if mode == "code_tests":

        if not execute_code:
            return {
                "status": "manual",
                "passed": None,
                "reason": (
                    "Automatic code "
                    "execution disabled."
                ),
            }

        return run_code_tests(
            text,
            expected["tests"],
        )

    # -----------------------------
    # Summaries
    # -----------------------------

    if mode == "summary_rubric":
        mechanical = {}

        normalized = clean(text)

        if "max_words" in expected:

            word_count = len(
                re.findall(
                    r"\b[\w'-]+\b",
                    normalized,
                )
            )

            mechanical[
                "word_count"
            ] = word_count

            mechanical[
                "max_words"
            ] = expected["max_words"]

            mechanical[
                "word_limit_pass"
            ] = (
                word_count
                <= expected["max_words"]
            )

        if "sentence_count" in expected:

            sentences = [
                part
                for part in re.split(
                    r"(?<=[.!?])\s+",
                    normalized,
                )
                if part.strip()
            ]

            mechanical[
                "sentence_count"
            ] = len(sentences)

            mechanical[
                "required_sentences"
            ] = expected[
                "sentence_count"
            ]

            mechanical[
                "sentence_count_pass"
            ] = (
                len(sentences)
                == expected[
                    "sentence_count"
                ]
            )

        if "max_bullets" in expected:

            bullets = [
                line
                for line
                in normalized.splitlines()
                if re.match(
                    r"^\s*(?:[-*•]|\d+[.)])\s+",
                    line,
                )
            ]

            mechanical[
                "bullet_count"
            ] = len(bullets)

            mechanical[
                "max_bullets"
            ] = expected["max_bullets"]

            mechanical[
                "bullet_limit_pass"
            ] = (
                len(bullets)
                <= expected[
                    "max_bullets"
                ]
            )

        return {
            "status": "manual",
            "passed": None,
            "reason": (
                "Semantic summary quality "
                "requires manual review."
            ),
            "mechanical_checks": mechanical,
            "must_include_concepts":
                expected.get(
                    "must_include_concepts",
                    [],
                ),
            "must_not_claim":
                expected.get(
                    "must_not_claim",
                    [],
                ),
        }

    return {
        "status": "manual",
        "passed": None,
        "reason": (
            f"Unknown grading mode: {mode}"
        ),
    }


# ---------------------------------------------------------
# Results summary
# ---------------------------------------------------------

def make_summary(
    results: list[dict],
) -> dict:

    auto = [
        row
        for row in results
        if row["grade"]["status"]
        in {"pass", "fail"}
    ]

    passed = [
        row
        for row in auto
        if row["grade"]["status"]
        == "pass"
    ]

    manual = [
        row
        for row in results
        if row["grade"]["status"]
        == "manual"
    ]

    errors = [
        row
        for row in results
        if row["grade"]["status"]
        == "error"
    ]

    latencies = [
        row["wall_time_seconds"]
        for row in results
        if row.get(
            "wall_time_seconds"
        ) is not None
    ]

    speeds = [
        row["response"].get(
            "tokens_per_second"
        )
        for row in results
        if row.get(
            "response",
            {},
        ).get(
            "tokens_per_second"
        ) is not None
    ]

    categories = sorted(
        {
            row["category"]
            for row in results
        }
    )

    by_category = {}

    for category in categories:

        rows = [
            row
            for row in results
            if row["category"]
            == category
        ]

        graded = [
            row
            for row in rows
            if row["grade"]["status"]
            in {"pass", "fail"}
        ]

        category_passed = [
            row
            for row in graded
            if row["grade"]["status"]
            == "pass"
        ]

        by_category[category] = {
            "total": len(rows),

            "auto_graded":
                len(graded),

            "passed":
                len(category_passed),

            "pass_rate_percent": (
                round(
                    100
                    * len(category_passed)
                    / len(graded),
                    1,
                )
                if graded
                else None
            ),

            "manual": len(
                [
                    row
                    for row in rows
                    if row[
                        "grade"
                    ][
                        "status"
                    ]
                    == "manual"
                ]
            ),
        }

    return {
        "total_cases":
            len(results),

        "auto_graded":
            len(auto),

        "passed":
            len(passed),

        "failed":
            len(auto) - len(passed),

        "pass_rate_percent": (
            round(
                100
                * len(passed)
                / len(auto),
                1,
            )
            if auto
            else None
        ),

        "manual_review":
            len(manual),

        "request_errors":
            len(errors),

        "average_wall_time_seconds": (
            round(
                statistics.mean(
                    latencies
                ),
                3,
            )
            if latencies
            else None
        ),

        "median_wall_time_seconds": (
            round(
                statistics.median(
                    latencies
                ),
                3,
            )
            if latencies
            else None
        ),

        "average_tokens_per_second": (
            round(
                statistics.mean(
                    speeds
                ),
                2,
            )
            if speeds
            else None
        ),

        "total_input_tokens": sum(
            int(
                row.get(
                    "response",
                    {},
                ).get(
                    "input_tokens"
                )
                or 0
            )
            for row in results
        ),

        "total_output_tokens": sum(
            int(
                row.get(
                    "response",
                    {},
                ).get(
                    "output_tokens"
                )
                or 0
            )
            for row in results
        ),

        "by_category":
            by_category,
    }


# ---------------------------------------------------------
# Save files
# ---------------------------------------------------------

def save_results(
    run_dir: Path,
    metadata: dict,
    results: list[dict],
) -> None:

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Complete machine-readable results.
    (
        run_dir
        / "raw_results.json"
    ).write_text(
        json.dumps(
            {
                "metadata": metadata,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Aggregate summary.
    summary = make_summary(
        results
    )

    (
        run_dir
        / "summary.json"
    ).write_text(
        json.dumps(
            {
                "metadata": metadata,
                "summary": summary,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Spreadsheet-friendly output.
    columns = [
        "id",
        "category",
        "difficulty",
        "quality",
        "model",
        "grade",
        "wall_time_seconds",
        "input_tokens",
        "output_tokens",
        "tokens_per_second",
        "time_to_first_token_seconds",
        "model_load_time_seconds",
        "response_text",
        "error",
    ]

    with (
        run_dir
        / "results.csv"
    ).open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=columns,
        )

        writer.writeheader()

        for row in results:

            response = row.get(
                "response",
                {},
            )

            writer.writerow(
                {
                    "id":
                        row["id"],

                    "category":
                        row["category"],

                    "difficulty":
                        row[
                            "difficulty"
                        ],

                    "quality":
                        row["quality"],

                    "model":
                        response.get(
                            "model"
                        ),

                    "grade":
                        row[
                            "grade"
                        ][
                            "status"
                        ],

                    "wall_time_seconds":
                        row.get(
                            "wall_time_seconds"
                        ),

                    "input_tokens":
                        response.get(
                            "input_tokens"
                        ),

                    "output_tokens":
                        response.get(
                            "output_tokens"
                        ),

                    "tokens_per_second":
                        response.get(
                            "tokens_per_second"
                        ),

                    "time_to_first_token_seconds":
                        response.get(
                            "time_to_first_token_seconds"
                        ),

                    "model_load_time_seconds":
                        response.get(
                            "model_load_time_seconds"
                        ),

                    "response_text":
                        response.get(
                            "text"
                        ),

                    "error":
                        row.get(
                            "error"
                        ),
                }
            )

    # Only things requiring human judgement.
    manual = [
        row
        for row in results
        if row["grade"]["status"]
        == "manual"
    ]

    (
        run_dir
        / "manual_review.json"
    ).write_text(
        json.dumps(
            manual,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------
# Main benchmark process
# ---------------------------------------------------------

def main() -> int:

    load_env(
        ROOT / ".env"
    )

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--quality",
        choices=[
            "fast",
            "balanced",
            "deep",
        ],
    )

    parser.add_argument(
        "--name",
    )

    parser.add_argument(
        "--category",
    )

    parser.add_argument(
        "--skip-code-tests",
        action="store_true",
    )

    args = parser.parse_args()

    gateway = os.getenv(
        "LOCAL_AI_GATEWAY_URL",
        "http://127.0.0.1:4812",
    )

    api_key = (
        os.getenv(
            "GATEWAY_API_KEY"
        )
        or os.getenv(
            "LOCAL_AI_GATEWAY_KEY"
        )
    )

    if not api_key:
        print(
            "GATEWAY_API_KEY "
            "was not found in .env.",
            file=sys.stderr,
        )
        return 2

    cases = load_cases()

    if args.category:

        cases = [
            case
            for case in cases
            if case["category"]
            == args.category
        ]

    timestamp = (
        datetime
        .now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    label = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        (
            args.name
            or args.quality
            or "benchmark"
        ),
    )

    run_dir = (
        RESULTS_DIR
        / f"{timestamp}_{label}"
    )

    metadata = {
        "started_at":
            datetime
            .now()
            .astimezone()
            .isoformat(),

        "forced_quality":
            args.quality,

        "name":
            args.name,

        "case_count":
            len(cases),
    }

    results = []

    headers = {
        "X-Local-AI-Key":
            api_key,

        "Content-Type":
            "application/json",
    }

    # -----------------------------------------------------
    # Connect to gateway
    # -----------------------------------------------------

    with httpx.Client(
        timeout=300
    ) as client:

        try:
            health = client.get(
                f"{gateway}/health"
            )

            health.raise_for_status()

        except Exception as error:

            print(
                "Gateway health check "
                f"failed: {error}",
                file=sys.stderr,
            )

            return 3

        # -------------------------------------------------
        # Run cases
        # -------------------------------------------------

        for number, case in enumerate(
            cases,
            1,
        ):

            defaults = case[
                "_defaults"
            ]

            quality = (
                args.quality
                or case.get(
                    "quality"
                )
                or defaults.get(
                    "quality",
                    "balanced",
                )
            )

            body = {
                "prompt":
                    case["prompt"],

                "quality":
                    quality,

                "temperature":
                    case.get(
                        "temperature",
                        defaults.get(
                            "temperature",
                            0.0,
                        ),
                    ),

                "max_output_tokens":
                    case.get(
                        "max_output_tokens",
                        2048,
                    ),
            }

            if case.get(
                "system"
            ):
                body["system"] = (
                    case["system"]
                )

            print(
                f"[{number:02d}/"
                f"{len(cases):02d}] "
                f"{case['id']} "
                f"({quality})",
                end=" ... ",
                flush=True,
            )

            start = (
                time.perf_counter()
            )

            result = {
                "id":
                    case["id"],

                "suite":
                    case["_suite"],

                "source_file":
                    case["_source"],

                "category":
                    case["category"],

                "difficulty":
                    case["difficulty"],

                "quality":
                    quality,

                "wall_time_seconds":
                    None,

                "response":
                    {},

                "grade":
                    {},

                "error":
                    None,
            }

            try:

                response = client.post(
                    f"{gateway}"
                    "/v1/generate",

                    headers=headers,
                    json=body,
                )

                result[
                    "wall_time_seconds"
                ] = round(
                    time.perf_counter()
                    - start,
                    3,
                )

                if not response.is_success:

                    result["error"] = (
                        f"HTTP "
                        f"{response.status_code}: "
                        f"{response.text}"
                    )

                    result["grade"] = {
                        "status":
                            "error",

                        "passed":
                            False,

                        "reason":
                            result[
                                "error"
                            ],
                    }

                    print("ERROR")

                else:

                    data = (
                        response.json()
                    )

                    result[
                        "response"
                    ] = data

                    result[
                        "grade"
                    ] = grade(
                        case,
                        data.get(
                            "text",
                            "",
                        ),
                        execute_code=(
                            not args
                            .skip_code_tests
                        ),
                    )

                    print(
                        result[
                            "grade"
                        ][
                            "status"
                        ].upper()
                    )

            except Exception as error:

                result[
                    "wall_time_seconds"
                ] = round(
                    time.perf_counter()
                    - start,
                    3,
                )

                result["error"] = (
                    repr(error)
                )

                result["grade"] = {
                    "status":
                        "error",

                    "passed":
                        False,

                    "reason":
                        repr(error),
                }

                print("ERROR")

            results.append(
                result
            )

            # Save after EVERY case.
            # If the benchmark crashes,
            # you don't lose the completed runs.

            run_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            (
                run_dir
                / "partial_results.json"
            ).write_text(
                json.dumps(
                    {
                        "metadata":
                            metadata,

                        "results":
                            results,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    # -----------------------------------------------------
    # Finished
    # -----------------------------------------------------

    metadata[
        "finished_at"
    ] = (
        datetime
        .now()
        .astimezone()
        .isoformat()
    )

    save_results(
        run_dir,
        metadata,
        results,
    )

    partial = (
        run_dir
        / "partial_results.json"
    )

    if partial.exists():
        partial.unlink()

    summary = make_summary(
        results
    )

    print()
    print(
        "=== BENCHMARK COMPLETE ==="
    )

    print(
        f"Cases:          "
        f"{summary['total_cases']}"
    )

    print(
        f"Auto graded:    "
        f"{summary['auto_graded']}"
    )

    print(
        f"Passed:         "
        f"{summary['passed']}"
    )

    print(
        f"Failed:         "
        f"{summary['failed']}"
    )

    print(
        f"Pass rate:      "
        f"{summary['pass_rate_percent']}%"
    )

    print(
        f"Manual review:  "
        f"{summary['manual_review']}"
    )

    print(
        f"Request errors: "
        f"{summary['request_errors']}"
    )

    print(
        f"Avg latency:    "
        f"{summary['average_wall_time_seconds']} s"
    )

    print(
        f"Avg tokens/sec: "
        f"{summary['average_tokens_per_second']}"
    )

    print()
    print(
        "Results folder:"
    )

    print(
        run_dir
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )