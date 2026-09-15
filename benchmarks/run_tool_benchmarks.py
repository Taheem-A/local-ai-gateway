"""Benchmark live tool selection, argument quality, and post-tool synthesis."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

BENCH_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BENCH_DIR / "results"
SUITE_PATH = BENCH_DIR / "tool_suite.json"


def _headers(api_key: str) -> dict[str, str]:
    return {"X-Local-AI-Key": api_key, "X-Project-ID": "tool-benchmark"}


def _normalized(value: Any) -> Any:
    """Normalize harmless string/numeric representation differences for grading."""

    if isinstance(value, str):
        return " ".join(value.strip().casefold().split())
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalized(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    return value


def _grade_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expect = case["expect"]
    expected_status = expect["status"]
    status_correct = result.get("status") == expected_status

    expected_calls = expect.get("calls", [])
    actual_calls = result.get("tool_calls") or []
    call_count_correct = len(actual_calls) == len(expected_calls)
    names_correct = call_count_correct
    arguments_correct = call_count_correct
    risks_correct = call_count_correct

    if expected_calls:
        # The v1 suite uses unique expected names, so matching by name keeps grading
        # independent of provider call ordering without hiding duplicate/missing calls.
        actual_by_name = {call.get("name"): call for call in actual_calls}
        if len(actual_by_name) != len(actual_calls):
            names_correct = arguments_correct = risks_correct = False
        for expected in expected_calls:
            actual = actual_by_name.get(expected["name"])
            if actual is None:
                names_correct = arguments_correct = risks_correct = False
                continue
            if _normalized(actual.get("arguments")) != _normalized(expected.get("arguments", {})):
                arguments_correct = False
            if actual.get("risk") != expected.get("risk"):
                risks_correct = False
    elif actual_calls:
        names_correct = arguments_correct = risks_correct = False

    text = result.get("text") or ""
    normalized_text = _normalized(text)
    contains_correct = all(
        _normalized(fragment) in normalized_text for fragment in expect.get("text_contains", [])
    )
    excludes_correct = all(
        _normalized(fragment) not in normalized_text
        for fragment in expect.get("text_not_contains", [])
    )

    selection_correct = status_correct and call_count_correct and names_correct
    case_success = (
        selection_correct
        and arguments_correct
        and risks_correct
        and contains_correct
        and excludes_correct
    )
    return {
        "status_correct": status_correct,
        "call_count_correct": call_count_correct,
        "tool_names_correct": names_correct,
        "arguments_correct": arguments_correct,
        "risk_annotations_correct": risks_correct,
        "text_contains_correct": contains_correct,
        "text_excludes_correct": excludes_correct,
        "selection_correct": selection_correct,
        "case_success": case_success,
    }


def main() -> int:
    """Run the fixed suite sequentially and save immutable comparison artifacts."""

    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gateway-url",
        default=os.getenv("LOCAL_AI_GATEWAY_URL", "http://127.0.0.1:4812"),
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("LOCAL_AI_GATEWAY_KEY") or os.getenv("GATEWAY_API_KEY"),
    )
    parser.add_argument("--quality", default="default")
    parser.add_argument("--reasoning", choices=["low", "medium", "high"], default=None)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--name", default="tool-calling-v1")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("Set LOCAL_AI_GATEWAY_KEY/GATEWAY_API_KEY or pass --api-key")

    suite_bytes = SUITE_PATH.read_bytes()
    suite = json.loads(suite_bytes.decode("utf-8"))
    suite_sha256 = hashlib.sha256(suite_bytes).hexdigest()
    base_url = args.gateway_url.rstrip("/")
    headers = _headers(args.api_key)
    rows: list[dict[str, Any]] = []
    total_started = time.perf_counter()

    with httpx.Client(timeout=300.0) as client:
        for case in suite["cases"]:
            body: dict[str, Any] = {
                "messages": case["messages"],
                "tools": case["tools"],
                "tool_choice": case.get("tool_choice", "auto"),
                "quality": args.quality,
                "max_output_tokens": args.max_output_tokens,
            }
            if args.reasoning:
                body["reasoning"] = args.reasoning

            started = time.perf_counter()
            response = client.post(
                f"{base_url}/v1/tools/turn",
                headers=headers,
                json=body,
            )
            latency = time.perf_counter() - started

            if response.is_success:
                result = response.json()
                grade = _grade_case(case, result)
                error = None
            else:
                try:
                    error_payload = response.json()
                except ValueError:
                    error_payload = {"raw": response.text}
                result = None
                grade = {
                    "status_correct": False,
                    "call_count_correct": False,
                    "tool_names_correct": False,
                    "arguments_correct": False,
                    "risk_annotations_correct": False,
                    "text_contains_correct": False,
                    "text_excludes_correct": False,
                    "selection_correct": False,
                    "case_success": False,
                }
                error = {"status_code": response.status_code, "payload": error_payload}

            row = {
                "id": case["id"],
                "tool_choice": body["tool_choice"],
                "expect": case["expect"],
                "result": result,
                "grade": grade,
                "latency_seconds": latency,
                "error": error,
            }
            rows.append(row)
            status = "PASS" if grade["case_success"] else "FAIL"
            result_status = result.get("status") if result else f"HTTP {response.status_code}"
            print(f"{case['id']}: {status} status={result_status} latency={latency:.3f}s")

    total_cases = len(rows)
    tool_cases = [row for row in rows if row["expect"].get("calls")]
    synthesis_cases = [
        row
        for row in rows
        if row["expect"].get("text_contains") or row["expect"].get("text_not_contains")
    ]
    latencies = [row["latency_seconds"] for row in rows]

    def percent(rows_to_score: list[dict[str, Any]], key: str) -> float:
        if not rows_to_score:
            return 100.0
        return 100.0 * sum(bool(row["grade"][key]) for row in rows_to_score) / len(rows_to_score)

    first_success = next((row["result"] for row in rows if row["result"]), {})
    summary = {
        "suite_version": suite["version"],
        "suite_sha256": suite_sha256,
        "quality": args.quality,
        "requested_reasoning": args.reasoning,
        "resolved_profile": first_success.get("profile"),
        "resolved_reasoning": first_success.get("reasoning"),
        "model": first_success.get("model"),
        "max_output_tokens": args.max_output_tokens,
        "cases": total_cases,
        "tool_request_cases": len(tool_cases),
        "synthesis_cases": len(synthesis_cases),
        "selection_accuracy_percent": round(percent(rows, "selection_correct"), 2),
        "argument_accuracy_percent": round(percent(tool_cases, "arguments_correct"), 2),
        "risk_annotation_accuracy_percent": round(
            percent(tool_cases, "risk_annotations_correct"), 2
        ),
        "synthesis_constraint_accuracy_percent": round(
            100.0
            * sum(
                row["grade"]["text_contains_correct"]
                and row["grade"]["text_excludes_correct"]
                for row in synthesis_cases
            )
            / len(synthesis_cases)
            if synthesis_cases
            else 100.0,
            2,
        ),
        "case_success_percent": round(percent(rows, "case_success"), 2),
        "request_errors": sum(row["error"] is not None for row in rows),
        "mean_latency_seconds": round(statistics.mean(latencies), 4),
        "median_latency_seconds": round(statistics.median(latencies), 4),
        "total_seconds": round(time.perf_counter() - total_started, 3),
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = RESULTS_DIR / f"{timestamp}_{args.name}_{uuid.uuid4().hex[:6]}"
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "raw_results.json").write_text(
        json.dumps({"summary": summary, "results": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    report = [
        "# Tool-calling benchmark",
        "",
        f"- Suite version: {summary['suite_version']}",
        f"- Suite SHA-256: `{summary['suite_sha256']}`",
        f"- Model: `{summary['model']}`",
        f"- Profile: `{summary['resolved_profile']}`",
        f"- Reasoning: `{summary['resolved_reasoning']}`",
        f"- Cases: {summary['cases']}",
        f"- Selection accuracy: {summary['selection_accuracy_percent']:.2f}%",
        f"- Argument accuracy: {summary['argument_accuracy_percent']:.2f}%",
        f"- Risk annotation accuracy: {summary['risk_annotation_accuracy_percent']:.2f}%",
        (
            "- Synthesis constraint accuracy: "
            f"{summary['synthesis_constraint_accuracy_percent']:.2f}%"
        ),
        f"- Full case success: {summary['case_success_percent']:.2f}%",
        f"- Request errors: {summary['request_errors']}",
        f"- Mean latency: {summary['mean_latency_seconds']:.4f}s",
        f"- Median latency: {summary['median_latency_seconds']:.4f}s",
        "",
        "| Case | Choice | Result | Selection | Args | Full pass | Latency (s) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        result_status = row["result"].get("status") if row["result"] else "error"
        report.append(
            f"| {row['id']} | {row['tool_choice']} | {result_status} | "
            f"{'yes' if row['grade']['selection_correct'] else 'no'} | "
            f"{'yes' if row['grade']['arguments_correct'] else 'no'} | "
            f"{'yes' if row['grade']['case_success'] else 'no'} | "
            f"{row['latency_seconds']:.4f} |"
        )
    (output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Saved to {output_dir}")
    return 0 if summary["case_success_percent"] == 100.0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
