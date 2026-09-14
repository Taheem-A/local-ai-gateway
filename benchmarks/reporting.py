"""Atomic benchmark result writers and aggregate score calculations."""

from __future__ import annotations

import csv
import io
import json
import os
import statistics
import tempfile
from pathlib import Path
from typing import Any

DIMENSIONS = ("semantic_correct", "format_correct", "instruction_following")
METRICS = (
    "input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "tokens_per_second",
    "time_to_first_token_seconds",
    "model_load_time_seconds",
)


def atomic_write(path: Path, text: str) -> None:
    """Replace one report file atomically so interrupted runs keep valid JSON/CSV."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _metric_summary(values: list[int | float]) -> dict[str, int | float | None]:
    """Calculate stable aggregate statistics for one numeric metric."""

    return {
        "observed": len(values),
        "mean": statistics.mean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "total": sum(values) if values else None,
    }


def make_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize independent grading dimensions, code tests, and performance data."""

    scores: dict[str, dict[str, int | float | None]] = {}
    for dimension in DIMENSIONS:
        values = [
            row["grade"].get(dimension)
            for row in results
            if row["grade"].get(dimension) is not None
        ]
        passed = sum(value is True for value in values)
        scores[dimension] = {
            "passed": passed,
            "evaluated": len(values),
            "percent": round(100 * passed / len(values), 1) if values else None,
        }

    tests = [test for row in results for test in row["grade"].get("tests", [])]
    performance: dict[str, dict[str, int | float | None]] = {}
    for metric in ("wall_time_seconds",) + METRICS:
        values = [
            row.get(metric)
            if metric == "wall_time_seconds"
            else row.get("response", {}).get(metric)
            for row in results
        ]
        numeric_values = [
            value for value in values if type(value) in (int, float)
        ]
        performance[metric] = _metric_summary(numeric_values)

    return {
        "total_cases": len(results),
        "scores": scores,
        "manual_review": sum(row["grade"]["status"] == "manual" for row in results),
        "errors": sum(row["grade"]["status"] == "error" for row in results),
        "code_tests": {
            "passed": sum(test["passed"] for test in tests),
            "evaluated": len(tests),
        },
        "performance": performance,
    }


def _manual_review_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a self-contained queue for cases that require human semantic review."""

    return [
        {
            "id": row["id"],
            "prompt": row.get("prompt"),
            "expected": row.get("expected"),
            "response_text": row.get("response", {}).get("text"),
            "grade": row["grade"],
            "review": {"semantic_correct": None, "notes": "", "reviewer": ""},
        }
        for row in results
        if row["grade"]["status"] == "manual"
    ]


def save_results(
    run_dir: Path,
    metadata: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    """Write all benchmark artifacts after each case for crash-safe checkpointing."""

    summary = make_summary(results)
    categories = sorted({row["category"] for row in results})
    summary["by_category"] = {
        category: make_summary(
            [row for row in results if row["category"] == category]
        )
        for category in categories
    }

    def write_json(name: str, value: Any) -> None:
        atomic_write(
            run_dir / name,
            json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False),
        )

    write_json("raw_results.json", {"metadata": metadata, "results": results})
    write_json("summary.json", {"metadata": metadata, "summary": summary})
    write_json("manual_review.json", _manual_review_rows(results))

    columns = (
        "id",
        "category",
        "difficulty",
        "quality",
        "reasoning",
        "model",
        "status",
    ) + DIMENSIONS + ("wall_time_seconds",) + METRICS + ("response_text", "error")

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in results:
        response = row.get("response", {})
        csv_row = {key: row.get(key) for key in columns}
        csv_row.update({key: response.get(key) for key in ("model",) + METRICS})
        csv_row.update(
            {key: row["grade"].get(key) for key in ("status",) + DIMENSIONS}
        )
        csv_row["response_text"] = response.get("text")
        writer.writerow(csv_row)
    atomic_write(run_dir / "results.csv", "\ufeff" + buffer.getvalue())

    benchmark_version = metadata.get("version", "unknown")
    lines = [
        f"# Benchmark v{benchmark_version}",
        "",
        f"Run state: {metadata.get('state')}; completed: {len(results)}/{metadata['case_count']}",
        "",
        "| Dimension | Passed / evaluated | Percent |",
        "|---|---:|---:|",
    ]
    for key, score in summary["scores"].items():
        lines.append(
            f"| {key} | {score['passed']} / {score['evaluated']} | {score['percent']} |"
        )

    lines += [
        "",
        f"Manual review: {summary['manual_review']}; errors: {summary['errors']}",
        "",
        "Manual cases and errors are excluded from dimensions with unknown scores.",
        "",
        "| Case | Semantic | Format | Instructions | Status |",
        "|---|---|---|---|---|",
    ]
    for row in results:
        grade = row["grade"]
        values = [row["id"]] + [grade.get(key) for key in DIMENSIONS] + [grade["status"]]
        lines.append("| " + " | ".join(str(value) for value in values) + " |")

    lines += [
        "",
        "Full timings and token statistics are in summary.json; prompts, grading policy, "
        "and original responses are in raw_results.json.",
        "",
    ]
    atomic_write(run_dir / "report.md", "\n".join(lines))
