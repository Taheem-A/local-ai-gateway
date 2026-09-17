"""Compare completed private Vision workload runs without invoking any model.

The comparator intentionally does not collapse multimodal quality and latency
into one arbitrary weighted score. It reports hard eligibility gates, manual
quality dimensions, and runtime cost side-by-side so the production decision is
traceable.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

SCORE_FIELDS = (
    "ocr_text_fidelity_0_2",
    "visual_spatial_accuracy_0_2",
    "reasoning_quality_0_2",
    "unsupported_claim_discipline_0_2",
    "instruction_following_0_2",
    "multi_image_correctness_0_2",
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 3) if values else None


def summarize_run(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    review_path = run_dir / "manual_review.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing {summary_path}")
    if not review_path.exists():
        raise FileNotFoundError(f"Missing {review_path}")

    summary = _load_json(summary_path)
    review = _load_json(review_path)
    scores = review.get("scores")
    if not isinstance(scores, list):
        raise ValueError(f"manual_review.json in {run_dir} has no scores array")

    dimension_values: dict[str, list[float]] = {field: [] for field in SCORE_FIELDS}
    incomplete = 0
    production_blockers = 0
    for item in scores:
        if not isinstance(item, dict):
            continue
        if item.get("production_blocker") is True:
            production_blockers += 1
        applicable = 0
        completed = 0
        for field in SCORE_FIELDS:
            value = item.get(field)
            if value is None:
                continue
            applicable += 1
            if isinstance(value, (int, float)) and 0 <= float(value) <= 2:
                dimension_values[field].append(float(value))
                completed += 1
            else:
                incomplete += 1
        if applicable == 0:
            incomplete += 1
        elif completed != applicable:
            incomplete += 1

    dimension_means = {field: _mean(values) for field, values in dimension_values.items()}
    manual_review_complete = bool(scores) and incomplete == 0 and any(
        value is not None for value in dimension_means.values()
    )
    request_errors = int(summary.get("request_errors") or 0)
    auto_accuracy = float(summary.get("automatic_case_accuracy_percent") or 0.0)

    return {
        "run": run_dir.name,
        "pipeline": summary.get("pipeline"),
        "vision_models": summary.get("vision_models") or [],
        "reason_models": summary.get("reason_models") or [],
        "cases": summary.get("cases"),
        "request_errors": request_errors,
        "automatic_case_accuracy_percent": auto_accuracy,
        "production_blockers": production_blockers,
        "manual_review_complete": manual_review_complete,
        "selection_eligible": request_errors == 0 and production_blockers == 0 and manual_review_complete,
        "manual_dimension_means": dimension_means,
        "mean_latency_seconds": summary.get("mean_latency_seconds"),
        "median_latency_seconds": summary.get("median_latency_seconds"),
        "mean_vision_ttft_seconds": summary.get("mean_vision_ttft_seconds"),
        "mean_vision_tokens_per_second": summary.get("mean_vision_tokens_per_second"),
        "mean_vision_model_load_seconds": summary.get("mean_vision_model_load_seconds"),
        "suite_sha256": summary.get("suite_sha256"),
        "runner_sha256": summary.get("runner_sha256"),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Vision workload comparison",
        "",
        "Selection policy: reject request errors or manual production blockers; require completed manual review; compare quality dimensions directly; use runtime cost as a tie-breaker rather than hiding trade-offs in one weighted score.",
        "",
        "| Run | Pipeline | Vision model | Eligible | Auto % | OCR | Visual/spatial | Reasoning | Unsupported discipline | Instruction | Multi-image | Mean latency |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        means = row["manual_dimension_means"]
        lines.append(
            "| {run} | {pipeline} | {model} | {eligible} | {auto:.2f} | {ocr} | {visual} | {reasoning} | {unsupported} | {instruction} | {multi} | {latency} |".format(
                run=row["run"],
                pipeline=row.get("pipeline") or "—",
                model=", ".join(row.get("vision_models") or []) or "—",
                eligible="yes" if row["selection_eligible"] else "no",
                auto=row["automatic_case_accuracy_percent"],
                ocr=_fmt(means["ocr_text_fidelity_0_2"]),
                visual=_fmt(means["visual_spatial_accuracy_0_2"]),
                reasoning=_fmt(means["reasoning_quality_0_2"]),
                unsupported=_fmt(means["unsupported_claim_discipline_0_2"]),
                instruction=_fmt(means["instruction_following_0_2"]),
                multi=_fmt(means["multi_image_correctness_0_2"]),
                latency=_fmt(row.get("mean_latency_seconds")),
            )
        )

    lines.extend(
        [
            "",
            "## Runtime details",
            "",
            "| Run | Mean TTFT | Mean tok/s | Mean model load | Errors | Blockers |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['run']} | {_fmt(row.get('mean_vision_ttft_seconds'))} | "
            f"{_fmt(row.get('mean_vision_tokens_per_second'))} | "
            f"{_fmt(row.get('mean_vision_model_load_seconds'))} | "
            f"{row['request_errors']} | {row['production_blockers']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="Completed Vision workload run directories")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args()

    rows = [summarize_run(path.resolve()) for path in args.runs]
    suite_hashes = {row.get("suite_sha256") for row in rows}
    if len(suite_hashes) > 1:
        parser.error("Runs use different workload suite hashes and are not directly comparable.")

    if args.json:
        print(json.dumps({"runs": rows}, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(rows), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
