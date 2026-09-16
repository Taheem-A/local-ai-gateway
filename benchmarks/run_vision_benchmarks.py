"""Run the fixed Stage 5 synthetic vision benchmark through the public gateway API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import statistics
import time
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version

BENCH_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BENCH_DIR / "results"
SUITE_PATH = BENCH_DIR / "vision_suite.json"
RUNNER_PATH = Path(__file__).resolve()


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return Pillow's bundled deterministic font at a readable synthetic size."""

    return ImageFont.load_default(size=size)


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str = "black",
) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width = right - left
    height = bottom - top
    x = box[0] + (box[2] - box[0] - width) / 2
    y = box[1] + (box[3] - box[1] - height) / 2
    draw.text((x, y), text, fill=fill, font=font)


def _fixture_shapes() -> list[bytes]:
    image = Image.new("RGB", (960, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((90, 150, 310, 370), fill="#d83232")
    draw.rectangle((370, 150, 590, 370), fill="#2878d0")
    draw.polygon([(760, 135), (645, 375), (875, 375)], fill="#2b9d4b")
    return [_png(image)]


def _fixture_text_reading() -> list[bytes]:
    image = Image.new("RGB", (960, 600), "#f7f5ef")
    draw = ImageDraw.Draw(image)
    title = _font(58)
    body = _font(48)
    draw.text((80, 80), "COURSE NOTICE", fill="#1f252b", font=title)
    draw.text((80, 220), "Course: CIV100", fill="#111111", font=body)
    draw.text((80, 315), "Room: SF1105", fill="#111111", font=body)
    draw.text((80, 410), "Due: 14:30", fill="#111111", font=body)
    return [_png(image)]


def _fixture_table_reading() -> list[bytes]:
    image = Image.new("RGB", (1080, 560), "white")
    draw = ImageDraw.Draw(image)
    header_font = _font(34)
    body_font = _font(42)
    x_positions = [40, 300, 790, 1040]
    y_positions = [90, 190, 410]
    for x in x_positions:
        draw.line((x, y_positions[0], x, y_positions[-1]), fill="#30343a", width=3)
    for y in y_positions:
        draw.line((x_positions[0], y, x_positions[-1], y), fill="#30343a", width=3)
    headers = ["COURSE", "TASK", "DUE TIME"]
    values = ["MAT186", "Problem Set 2", "23:59"]
    for index, text in enumerate(headers):
        _centered_text(
            draw,
            (x_positions[index], 90, x_positions[index + 1], 190),
            text,
            font=header_font,
            fill="#4d545d",
        )
    for index, text in enumerate(values):
        _centered_text(
            draw,
            (x_positions[index], 190, x_positions[index + 1], 410),
            text,
            font=body_font,
        )
    return [_png(image)]


def _fixture_spatial_relation() -> list[bytes]:
    image = Image.new("RGB", (960, 560), "#fafafa")
    draw = ImageDraw.Draw(image)
    draw.rectangle((120, 170, 350, 400), fill="#ef8b23")
    draw.ellipse((610, 170, 840, 400), fill="#7a43b6")
    return [_png(image)]


def _number_image(number: str) -> bytes:
    image = Image.new("RGB", (600, 460), "white")
    draw = ImageDraw.Draw(image)
    _centered_text(
        draw,
        (0, 0, 600, 460),
        number,
        font=_font(170),
        fill="#14171a",
    )
    return _png(image)


def _fixture_multi_image() -> list[bytes]:
    return [_number_image("17"), _number_image("23")]


def _fixture_ui_error() -> list[bytes]:
    image = Image.new("RGB", (1000, 620), "#15191e")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (130, 105, 870, 515),
        radius=18,
        fill="#232931",
        outline="#545c66",
        width=3,
    )
    draw.text((190, 160), "LOCAL GATEWAY", fill="#e7e9ec", font=_font(44))
    draw.text((190, 285), "Status: DISCONNECTED", fill="#ffbb55", font=_font(42))
    draw.text((190, 370), "Error: E_CONN_4812", fill="#ff6b72", font=_font(42))
    return [_png(image)]


_FIXTURES = {
    "shapes": _fixture_shapes,
    "text_reading": _fixture_text_reading,
    "table_reading": _fixture_table_reading,
    "spatial_relation": _fixture_spatial_relation,
    "multi_image": _fixture_multi_image,
    "ui_error": _fixture_ui_error,
}


def build_fixture(name: str) -> list[bytes]:
    """Build one deterministic benchmark fixture without external image assets."""

    try:
        builder = _FIXTURES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown vision fixture: {name}") from exc
    return builder()


def grade_text(text: str, expected_all: list[str]) -> dict[str, Any]:
    """Grade only explicit visible facts using case-insensitive substring checks."""

    normalized = " ".join(text.casefold().split())
    missing = [term for term in expected_all if term.casefold() not in normalized]
    return {
        "expected_terms": expected_all,
        "missing_terms": missing,
        "fact_correct": not missing,
    }


def _image_payload(raw: bytes) -> dict[str, str]:
    return {
        "media_type": "image/png",
        "data_base64": base64.b64encode(raw).decode("ascii"),
    }


def _headers(api_key: str) -> dict[str, str]:
    return {
        "X-Local-AI-Key": api_key,
        "X-Project-ID": "vision-benchmark",
        "Content-Type": "application/json",
    }


def _percent(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    passed = sum(bool(row["grade"].get(field)) for row in rows)
    return round(100.0 * passed / len(rows), 2)


def main() -> int:
    """Run the fixed suite sequentially and save immutable-ready artifacts."""

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
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--name", default="vision-v1")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("Set LOCAL_AI_GATEWAY_KEY/GATEWAY_API_KEY or pass --api-key")

    suite_bytes = SUITE_PATH.read_bytes()
    suite = json.loads(suite_bytes.decode("utf-8"))
    suite_sha256 = hashlib.sha256(suite_bytes).hexdigest()
    runner_sha256 = hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest()
    base_url = args.gateway_url.rstrip("/")
    rows: list[dict[str, Any]] = []
    fixture_snapshots: dict[str, list[bytes]] = {}
    total_started = time.perf_counter()

    with httpx.Client(timeout=300.0) as client:
        for case in suite["cases"]:
            fixture_images = build_fixture(case["fixture"])
            fixture_snapshots[case["id"]] = fixture_images
            body = {
                "prompt": case["prompt"],
                "images": [_image_payload(raw) for raw in fixture_images],
                "temperature": 0.0,
                "max_output_tokens": args.max_output_tokens,
            }
            started = time.perf_counter()
            payload: dict[str, Any] | None = None
            error: dict[str, Any] | None = None

            try:
                response = client.post(
                    f"{base_url}/v1/vision",
                    headers=_headers(args.api_key),
                    json=body,
                )
                try:
                    parsed = response.json()
                except ValueError:
                    parsed = None
                if response.is_success and isinstance(parsed, dict):
                    payload = parsed
                else:
                    error = {
                        "status": response.status_code,
                        "body": parsed if parsed is not None else response.text,
                    }
            except httpx.HTTPError as exc:
                error = {"exception": type(exc).__name__, "message": str(exc)}

            latency = time.perf_counter() - started
            text = str(payload.get("text") or "") if payload else ""
            grade = grade_text(text, list(case["expected_all"]))
            if error is not None:
                grade["fact_correct"] = False

            row = {
                "id": case["id"],
                "fixture": case["fixture"],
                "prompt": case["prompt"],
                "expected_all": case["expected_all"],
                "text": text,
                "model": payload.get("model") if payload else None,
                "request_id": payload.get("request_id") if payload else None,
                "input_tokens": payload.get("input_tokens") if payload else None,
                "output_tokens": payload.get("output_tokens") if payload else None,
                "reasoning_output_tokens": (
                    payload.get("reasoning_output_tokens") if payload else None
                ),
                "tokens_per_second": payload.get("tokens_per_second") if payload else None,
                "model_load_time_seconds": (
                    payload.get("model_load_time_seconds") if payload else None
                ),
                "latency_seconds": latency,
                "grade": grade,
                "error": error,
            }
            rows.append(row)
            status = "pass" if grade["fact_correct"] else "FAIL"
            print(
                f"{case['id']}: {status} latency={latency:.3f}s "
                f"missing={grade['missing_terms']}"
            )

    latencies = [float(row["latency_seconds"]) for row in rows]
    models = sorted({str(row["model"]) for row in rows if row.get("model")})
    summary = {
        "suite_version": suite["version"],
        "suite_sha256": suite_sha256,
        "runner_sha256": runner_sha256,
        "pillow_version": pillow_version,
        "cases": len(rows),
        "models": models,
        "fact_accuracy_percent": _percent(rows, "fact_correct"),
        "request_errors": sum(row["error"] is not None for row in rows),
        "mean_latency_seconds": round(statistics.mean(latencies), 4),
        "median_latency_seconds": round(statistics.median(latencies), 4),
        "total_seconds": round(time.perf_counter() - total_started, 3),
        "production_gate_passed": (
            _percent(rows, "fact_correct") == 100.0
            and not any(row["error"] is not None for row in rows)
            and len(models) == 1
        ),
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(
        char if char.isalnum() or char in "-_" else "-" for char in args.name
    )
    run_dir = RESULTS_DIR / f"{timestamp}_{safe_name}_{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    fixture_dir = run_dir / "fixtures"
    fixture_dir.mkdir()
    for case_id, images in fixture_snapshots.items():
        for index, raw in enumerate(images, start=1):
            (fixture_dir / f"{case_id}_{index}.png").write_bytes(raw)

    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "raw_results.json").write_text(
        json.dumps({"summary": summary, "results": rows}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    report = [
        "# Vision benchmark",
        "",
        f"- Suite version: `{summary['suite_version']}`",
        f"- Suite SHA-256: `{summary['suite_sha256']}`",
        f"- Runner SHA-256: `{summary['runner_sha256']}`",
        f"- Pillow: `{summary['pillow_version']}`",
        f"- Model(s): `{', '.join(models) if models else 'none'}`",
        f"- Cases: {summary['cases']}",
        f"- Fact accuracy: {summary['fact_accuracy_percent']:.2f}%",
        f"- Request errors: {summary['request_errors']}",
        f"- Mean latency: {summary['mean_latency_seconds']}s",
        f"- Median latency: {summary['median_latency_seconds']}s",
        f"- Production gate passed: {summary['production_gate_passed']}",
        "",
        "| Case | Pass | Missing terms | Latency (s) |",
        "|---|---:|---|---:|",
    ]
    for row in rows:
        missing = ", ".join(row["grade"]["missing_terms"]) or "—"
        report.append(
            f"| {row['id']} | {'yes' if row['grade']['fact_correct'] else 'no'} | "
            f"{missing} | {row['latency_seconds']:.4f} |"
        )
    (run_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Saved to {run_dir}")
    return 0 if summary["production_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
