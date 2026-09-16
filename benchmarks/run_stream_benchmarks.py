"""Benchmark the public SSE streaming contract and incremental delivery latency."""

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
SUITE_PATH = BENCH_DIR / "stream_suite.json"
ALLOWED_EVENT_TYPES = {"start", "progress", "delta", "completed", "error"}


class SSEDecoder:
    """Decode the gateway's named JSON SSE events for benchmark inspection."""

    def __init__(self) -> None:
        self.event_name: str | None = None
        self.data_lines: list[str] = []

    def feed(self, line: str) -> dict[str, Any] | None:
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return None
        field, separator, value = line.partition(":")
        if not separator:
            return None
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self.event_name = value
        elif field == "data":
            self.data_lines.append(value)
        return None

    def finish(self) -> dict[str, Any] | None:
        return self._dispatch()

    def _dispatch(self) -> dict[str, Any] | None:
        if not self.data_lines:
            self.event_name = None
            return None
        event_name = self.event_name
        raw = "\n".join(self.data_lines)
        self.event_name = None
        self.data_lines = []
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("SSE payload was not a JSON object")
        payload.setdefault("type", event_name)
        return payload


def _headers(api_key: str) -> dict[str, str]:
    return {
        "X-Local-AI-Key": api_key,
        "X-Project-ID": "stream-benchmark",
        "Accept": "text/event-stream",
    }


def _grade_case(
    case: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    first_text_latency: float | None,
    total_latency: float,
) -> dict[str, Any]:
    event_types = [str(event.get("type") or "") for event in events]
    completed_events = [event for event in events if event.get("type") == "completed"]
    deltas = [
        str(event.get("text") or "")
        for event in events
        if event.get("type") == "delta"
    ]
    reconstructed = "".join(deltas).strip()
    completed = completed_events[0] if len(completed_events) == 1 else {}
    completed_text = str(completed.get("text") or "").strip()

    request_ids = {
        str(event["request_id"])
        for event in events
        if isinstance(event.get("request_id"), str) and event.get("request_id")
    }
    all_have_request_id = bool(events) and all(
        isinstance(event.get("request_id"), str) and bool(event.get("request_id"))
        for event in events
    )

    protocol_correct = (
        bool(event_types)
        and event_types[0] == "start"
        and event_types[-1] == "completed"
        and set(event_types).issubset(ALLOWED_EVENT_TYPES)
        and event_types.count("completed") == 1
        and "error" not in event_types
    )
    aggregate_match = bool(reconstructed) and reconstructed == completed_text
    incremental_delivery = len(deltas) >= int(case.get("min_delta_count", 1))
    request_id_consistent = all_have_request_id and len(request_ids) == 1
    timing_valid = first_text_latency is not None and 0 <= first_text_latency <= total_latency
    metadata_valid = (
        isinstance(completed.get("model"), str)
        and bool(completed.get("model"))
        and isinstance(completed.get("profile"), str)
        and isinstance(completed.get("total_latency_seconds"), (int, float))
    )

    case_success = (
        protocol_correct
        and aggregate_match
        and incremental_delivery
        and request_id_consistent
        and timing_valid
        and metadata_valid
    )
    return {
        "protocol_correct": protocol_correct,
        "aggregate_match": aggregate_match,
        "incremental_delivery": incremental_delivery,
        "request_id_consistent": request_id_consistent,
        "timing_valid": timing_valid,
        "metadata_valid": metadata_valid,
        "case_success": case_success,
        "delta_count": len(deltas),
        "reconstructed_text": reconstructed,
        "completed_text": completed_text,
    }


def _percent(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    return round(100.0 * sum(bool(row["grade"].get(field)) for row in rows) / len(rows), 2)


def main() -> int:
    """Run the fixed stream suite sequentially and save reproducible artifacts."""

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
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--name", default="streaming-v1")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("Set LOCAL_AI_GATEWAY_KEY/GATEWAY_API_KEY or pass --api-key")

    suite_bytes = SUITE_PATH.read_bytes()
    suite = json.loads(suite_bytes.decode("utf-8"))
    suite_sha256 = hashlib.sha256(suite_bytes).hexdigest()
    base_url = args.gateway_url.rstrip("/")
    rows: list[dict[str, Any]] = []
    total_started = time.perf_counter()

    with httpx.Client(timeout=300.0) as client:
        for case in suite["cases"]:
            body: dict[str, Any] = {
                "prompt": case["prompt"],
                "quality": args.quality,
                "max_output_tokens": args.max_output_tokens,
            }
            if args.reasoning:
                body["reasoning"] = args.reasoning

            started = time.perf_counter()
            events: list[dict[str, Any]] = []
            first_text_latency: float | None = None
            http_error: dict[str, Any] | None = None

            try:
                with client.stream(
                    "POST",
                    f"{base_url}/v1/generate/stream",
                    headers=_headers(args.api_key),
                    json=body,
                ) as response:
                    if not response.is_success:
                        response.read()
                        try:
                            http_error = response.json()
                        except ValueError:
                            http_error = {"status": response.status_code, "text": response.text}
                    else:
                        decoder = SSEDecoder()
                        for line in response.iter_lines():
                            event = decoder.feed(line)
                            if event is None:
                                continue
                            if event.get("type") == "delta" and first_text_latency is None:
                                first_text_latency = time.perf_counter() - started
                            events.append(event)
                        trailing = decoder.finish()
                        if trailing is not None:
                            if trailing.get("type") == "delta" and first_text_latency is None:
                                first_text_latency = time.perf_counter() - started
                            events.append(trailing)
            except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                http_error = {"exception": type(exc).__name__, "message": str(exc)}

            total_latency = time.perf_counter() - started
            if http_error is None:
                grade = _grade_case(
                    case,
                    events,
                    first_text_latency=first_text_latency,
                    total_latency=total_latency,
                )
            else:
                grade = {
                    "protocol_correct": False,
                    "aggregate_match": False,
                    "incremental_delivery": False,
                    "request_id_consistent": False,
                    "timing_valid": False,
                    "metadata_valid": False,
                    "case_success": False,
                    "delta_count": 0,
                    "reconstructed_text": "",
                    "completed_text": "",
                }

            completed = next(
                (event for event in events if event.get("type") == "completed"),
                None,
            )
            row = {
                "id": case["id"],
                "first_text_latency_seconds": first_text_latency,
                "total_latency_seconds": total_latency,
                "events": events,
                "completed": completed,
                "grade": grade,
                "error": http_error,
            }
            rows.append(row)
            status = "pass" if grade["case_success"] else "FAIL"
            first = "n/a" if first_text_latency is None else f"{first_text_latency:.4f}s"
            print(
                f"{case['id']}: {status} deltas={grade['delta_count']} "
                f"first_text={first} total={total_latency:.4f}s"
            )

    first_text_values = [
        float(row["first_text_latency_seconds"])
        for row in rows
        if row["first_text_latency_seconds"] is not None
    ]
    total_values = [float(row["total_latency_seconds"]) for row in rows]
    completed_payloads = [row["completed"] for row in rows if row["completed"]]
    exemplar = completed_payloads[0] if completed_payloads else {}

    summary = {
        "suite_version": suite["version"],
        "suite_sha256": suite_sha256,
        "quality": args.quality,
        "requested_reasoning": args.reasoning,
        "resolved_profile": exemplar.get("profile"),
        "resolved_reasoning": exemplar.get("reasoning"),
        "model": exemplar.get("model"),
        "max_output_tokens": args.max_output_tokens,
        "cases": len(rows),
        "protocol_accuracy_percent": _percent(rows, "protocol_correct"),
        "aggregate_match_percent": _percent(rows, "aggregate_match"),
        "incremental_delivery_percent": _percent(rows, "incremental_delivery"),
        "request_id_consistency_percent": _percent(rows, "request_id_consistent"),
        "case_success_percent": _percent(rows, "case_success"),
        "request_errors": sum(row["error"] is not None for row in rows),
        "mean_first_text_latency_seconds": (
            round(statistics.mean(first_text_values), 4) if first_text_values else None
        ),
        "median_first_text_latency_seconds": (
            round(statistics.median(first_text_values), 4) if first_text_values else None
        ),
        "mean_total_latency_seconds": round(statistics.mean(total_values), 4),
        "median_total_latency_seconds": round(statistics.median(total_values), 4),
        "mean_delta_count": round(
            statistics.mean(row["grade"]["delta_count"] for row in rows),
            2,
        ),
        "total_seconds": round(time.perf_counter() - total_started, 3),
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(char if char.isalnum() or char in "-_" else "-" for char in args.name)
    run_dir = RESULTS_DIR / f"{timestamp}_{safe_name}_{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "raw_results.json").write_text(
        json.dumps({"summary": summary, "results": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report_lines = [
        "# Streaming benchmark",
        "",
        f"- Suite version: {summary['suite_version']}",
        f"- Suite SHA-256: `{summary['suite_sha256']}`",
        f"- Model: `{summary['model']}`",
        f"- Profile: `{summary['resolved_profile']}`",
        f"- Reasoning: `{summary['resolved_reasoning']}`",
        f"- Cases: {summary['cases']}",
        f"- Protocol accuracy: {summary['protocol_accuracy_percent']:.2f}%",
        f"- Aggregate match: {summary['aggregate_match_percent']:.2f}%",
        f"- Incremental delivery: {summary['incremental_delivery_percent']:.2f}%",
        f"- Request-ID consistency: {summary['request_id_consistency_percent']:.2f}%",
        f"- Full case success: {summary['case_success_percent']:.2f}%",
        f"- Request errors: {summary['request_errors']}",
        f"- Mean first-text latency: {summary['mean_first_text_latency_seconds']}s",
        f"- Median first-text latency: {summary['median_first_text_latency_seconds']}s",
        f"- Mean total latency: {summary['mean_total_latency_seconds']}s",
        f"- Median total latency: {summary['median_total_latency_seconds']}s",
        f"- Mean delta count: {summary['mean_delta_count']}",
        "",
        "| Case | Pass | Deltas | First text (s) | Total (s) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        first = row["first_text_latency_seconds"]
        report_lines.append(
            f"| {row['id']} | {'yes' if row['grade']['case_success'] else 'no'} | "
            f"{row['grade']['delta_count']} | "
            f"{first if first is not None else 'n/a'} | {row['total_latency_seconds']:.4f} |"
        )
    (run_dir / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Saved to {run_dir}")
    return 0 if summary["case_success_percent"] == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
