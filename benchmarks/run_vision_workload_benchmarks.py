"""Benchmark realistic local Vision workloads through the public gateway API.

The tracked suite is only a template. Real screenshots/photos stay local and are
referenced by a private `benchmarks/vision_workload.local.json` manifest.

Two pipelines are supported:
- direct: the configured VLM answers the task itself.
- vision-then-reason: the VLM extracts evidence, then `/v1/generate` performs
  the final reasoning step using only that evidence.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
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
DEFAULT_SUITE = BENCH_DIR / "vision_workload.local.json"
RUNNER_PATH = Path(__file__).resolve()
_ALLOWED_MEDIA = {"image/png", "image/jpeg", "image/webp"}


def _headers(api_key: str, project: str) -> dict[str, str]:
    return {
        "X-Local-AI-Key": api_key,
        "X-Project-ID": project,
        "Content-Type": "application/json",
    }


def _image_payload(path: Path) -> dict[str, str]:
    media_type = mimetypes.guess_type(path.name)[0]
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    if media_type not in _ALLOWED_MEDIA:
        raise ValueError(f"Unsupported workload image type for {path}: {media_type}")
    raw = path.read_bytes()
    return {
        "media_type": media_type,
        "data_base64": base64.b64encode(raw).decode("ascii"),
    }


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def grade_text(text: str, expected_all: list[str], forbidden_any: list[str]) -> dict[str, Any]:
    normalized = _normalize(text)
    missing = [term for term in expected_all if _normalize(term) not in normalized]
    forbidden_hits = [term for term in forbidden_any if _normalize(term) in normalized]
    return {
        "missing_terms": missing,
        "forbidden_hits": forbidden_hits,
        "expected_facts_correct": not missing,
        "hallucination_guard_passed": not forbidden_hits,
        "automatic_pass": not missing and not forbidden_hits,
    }


def _post_json(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        return None, {"exception": type(exc).__name__, "message": str(exc)}
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if response.is_success and isinstance(payload, dict):
        return payload, None
    return None, {
        "status": response.status_code,
        "body": payload if payload is not None else response.text,
    }


def _vision_request(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    *,
    prompt: str,
    images: list[dict[str, str]],
    max_output_tokens: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    return _post_json(
        client,
        f"{base_url}/v1/vision",
        headers=headers,
        body={
            "prompt": prompt,
            "images": images,
            "temperature": 0.0,
            "max_output_tokens": max_output_tokens,
        },
    )


def _reason_request(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    *,
    task: str,
    evidence: str,
    quality: str,
    max_output_tokens: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    prompt = (
        "You are the reasoning stage of a vision pipeline. The text below was produced "
        "by a separate vision model from the user's images. Use only that evidence; do "
        "not invent unseen visual facts. If the evidence is insufficient, say so.\n\n"
        f"ORIGINAL TASK:\n{task}\n\nVISUAL EVIDENCE:\n{evidence}"
    )
    return _post_json(
        client,
        f"{base_url}/v1/generate",
        headers=headers,
        body={
            "prompt": prompt,
            "quality": quality,
            "temperature": 0.0,
            "max_output_tokens": max_output_tokens,
        },
    )


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument(
        "--gateway-url",
        default=os.getenv("LOCAL_AI_GATEWAY_URL", "http://127.0.0.1:4812"),
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("LOCAL_AI_GATEWAY_KEY") or os.getenv("GATEWAY_API_KEY"),
    )
    parser.add_argument("--pipeline", choices=("direct", "vision-then-reason"), default="direct")
    parser.add_argument("--reason-quality", default="default")
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--name", default="vision-workload-v1")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("Set LOCAL_AI_GATEWAY_KEY/GATEWAY_API_KEY or pass --api-key")
    suite_path = args.suite.resolve()
    if not suite_path.exists():
        parser.error(
            f"Workload suite not found: {suite_path}. Copy "
            "benchmarks/vision_workload_suite.example.json to "
            "benchmarks/vision_workload.local.json and point it at your private images."
        )

    suite_bytes = suite_path.read_bytes()
    suite = json.loads(suite_bytes.decode("utf-8"))
    if not isinstance(suite.get("cases"), list) or not suite["cases"]:
        parser.error("The workload suite must contain a non-empty cases array.")

    suite_sha = hashlib.sha256(suite_bytes).hexdigest()
    runner_sha = hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest()
    base_url = args.gateway_url.rstrip("/")
    headers = _headers(args.api_key, f"vision-workload-{args.pipeline}")
    rows: list[dict[str, Any]] = []
    total_started = time.perf_counter()

    with httpx.Client(timeout=300.0) as client:
        for case in suite["cases"]:
            case_started = time.perf_counter()
            image_paths = [
                (suite_path.parent / item).resolve() for item in case.get("images", [])
            ]
            missing_files = [str(path) for path in image_paths if not path.exists()]
            if missing_files:
                row = {
                    "id": case.get("id"),
                    "category": case.get("category"),
                    "error": {"missing_files": missing_files},
                    "grade": {
                        "expected_facts_correct": False,
                        "hallucination_guard_passed": False,
                        "automatic_pass": False,
                    },
                    "latency_seconds": time.perf_counter() - case_started,
                }
                rows.append(row)
                print(f"{case.get('id')}: FAIL missing files")
                continue

            images = [_image_payload(path) for path in image_paths]
            evidence_prompt = case.get(
                "evidence_prompt",
                "Extract the question-relevant visual evidence precisely. Quote important visible text exactly. Separate direct observations from uncertainty. Do not solve beyond what the image itself establishes.",
            )
            vision_prompt = case["prompt"] if args.pipeline == "direct" else evidence_prompt
            vision_payload, vision_error = _vision_request(
                client,
                base_url,
                headers,
                prompt=vision_prompt,
                images=images,
                max_output_tokens=args.max_output_tokens,
            )
            final_payload = vision_payload
            reason_payload = None
            error = vision_error

            if args.pipeline == "vision-then-reason" and vision_payload is not None:
                reason_payload, reason_error = _reason_request(
                    client,
                    base_url,
                    headers,
                    task=case["prompt"],
                    evidence=str(vision_payload.get("text") or ""),
                    quality=args.reason_quality,
                    max_output_tokens=args.max_output_tokens,
                )
                final_payload = reason_payload
                error = reason_error

            text = str(final_payload.get("text") or "") if final_payload else ""
            grade = grade_text(
                text,
                list(case.get("expected_all") or []),
                list(case.get("forbidden_any") or []),
            )
            if error is not None:
                grade["automatic_pass"] = False

            row = {
                "id": case["id"],
                "category": case.get("category", "uncategorized"),
                "pipeline": args.pipeline,
                "image_files": [path.name for path in image_paths],
                "prompt": case["prompt"],
                "expected_all": case.get("expected_all", []),
                "forbidden_any": case.get("forbidden_any", []),
                "vision_text": str(vision_payload.get("text") or "") if vision_payload else "",
                "final_text": text,
                "vision_model": vision_payload.get("model") if vision_payload else None,
                "reason_model": reason_payload.get("model") if reason_payload else None,
                "vision_request_id": vision_payload.get("request_id") if vision_payload else None,
                "reason_request_id": reason_payload.get("request_id") if reason_payload else None,
                "grade": grade,
                "latency_seconds": time.perf_counter() - case_started,
                "error": error,
            }
            rows.append(row)
            status = "pass" if grade["automatic_pass"] else "FAIL"
            print(
                f"{case['id']}: {status} latency={row['latency_seconds']:.3f}s "
                f"missing={grade['missing_terms']} forbidden={grade['forbidden_hits']}"
            )

    valid_latencies = [float(row["latency_seconds"]) for row in rows]
    passed = sum(bool(row["grade"].get("automatic_pass")) for row in rows)
    request_errors = sum(row.get("error") is not None for row in rows)
    vision_models = sorted({str(row.get("vision_model")) for row in rows if row.get("vision_model")})
    reason_models = sorted({str(row.get("reason_model")) for row in rows if row.get("reason_model")})
    summary = {
        "suite_version": suite.get("version", "unknown"),
        "suite_sha256": suite_sha,
        "runner_sha256": runner_sha,
        "pipeline": args.pipeline,
        "reason_quality": args.reason_quality if args.pipeline == "vision-then-reason" else None,
        "cases": len(rows),
        "automatic_case_accuracy_percent": round(100.0 * passed / len(rows), 2) if rows else 0.0,
        "request_errors": request_errors,
        "vision_models": vision_models,
        "reason_models": reason_models,
        "mean_latency_seconds": _mean(valid_latencies),
        "median_latency_seconds": _median(valid_latencies),
        "total_seconds": round(time.perf_counter() - total_started, 3),
        "manual_review_required": True,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(char if char.isalnum() or char in "-_" else "-" for char in args.name)
    run_dir = RESULTS_DIR / f"{timestamp}_{safe_name}_{args.pipeline}_{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "raw_results.json").write_text(
        json.dumps({"summary": summary, "results": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manual = {
        "instructions": (
            "Review each answer against the actual images. Score 0-2 for OCR/text fidelity, "
            "visual/spatial accuracy, reasoning quality, and unsupported-claim discipline. "
            "Do not change automatic grades after seeing model outputs."
        ),
        "scores": [
            {
                "id": row.get("id"),
                "ocr_text_fidelity_0_2": None,
                "visual_spatial_accuracy_0_2": None,
                "reasoning_quality_0_2": None,
                "unsupported_claim_discipline_0_2": None,
                "notes": "",
            }
            for row in rows
        ],
    }
    (run_dir / "manual_review.json").write_text(
        json.dumps(manual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    report = [
        "# Vision workload benchmark",
        "",
        f"- Suite: `{summary['suite_version']}`",
        f"- Suite SHA-256: `{summary['suite_sha256']}`",
        f"- Pipeline: `{summary['pipeline']}`",
        f"- Vision model(s): `{', '.join(vision_models) if vision_models else 'none'}`",
        f"- Reason model(s): `{', '.join(reason_models) if reason_models else 'none'}`",
        f"- Cases: {summary['cases']}",
        f"- Automatic case accuracy: {summary['automatic_case_accuracy_percent']:.2f}%",
        f"- Request errors: {summary['request_errors']}",
        f"- Mean latency: {summary['mean_latency_seconds']}s",
        f"- Median latency: {summary['median_latency_seconds']}s",
        "- Manual review: required before model/pipeline selection",
        "",
        "| Case | Category | Pass | Latency (s) |",
        "|---|---|---:|---:|",
    ]
    for row in rows:
        report.append(
            f"| {row.get('id')} | {row.get('category')} | "
            f"{'yes' if row['grade'].get('automatic_pass') else 'no'} | "
            f"{float(row['latency_seconds']):.4f} |"
        )
    (run_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Saved to {run_dir}")
    return 1 if request_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
