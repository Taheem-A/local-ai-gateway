"""Compare committed benchmark summary files without invoking a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_summary(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load one summary artifact and return its metadata plus summary payload."""

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("metadata", {}), payload["summary"]


def label_for(path: Path, metadata: dict[str, Any]) -> str:
    """Choose a stable human-readable label for one run."""

    return str(metadata.get("name") or path.parent.name)


def cell(value: Any, digits: int = 2) -> str:
    """Render nullable numeric values consistently in the comparison table."""

    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def build_rows(entries: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, list[str]]]:
    """Extract the key quality and performance dimensions used for routing decisions."""

    rows: list[tuple[str, list[str]]] = []
    score_keys = (
        ("Semantic correct (%)", "semantic_correct"),
        ("Format correct (%)", "format_correct"),
        ("Instruction following (%)", "instruction_following"),
    )
    for title, key in score_keys:
        rows.append(
            (
                title,
                [cell(summary["scores"][key]["percent"], 1) for _, summary in entries],
            )
        )

    rows.extend(
        [
            (
                "Mean latency (s)",
                [
                    cell(summary["performance"]["wall_time_seconds"]["mean"], 2)
                    for _, summary in entries
                ],
            ),
            (
                "Median latency (s)",
                [
                    cell(summary["performance"]["wall_time_seconds"]["median"], 2)
                    for _, summary in entries
                ],
            ),
            (
                "Reasoning tokens",
                [
                    cell(summary["performance"]["reasoning_output_tokens"]["total"], 0)
                    for _, summary in entries
                ],
            ),
            (
                "Output tokens",
                [
                    cell(summary["performance"]["output_tokens"]["total"], 0)
                    for _, summary in entries
                ],
            ),
            ("Errors", [cell(summary["errors"]) for _, summary in entries]),
            (
                "Code tests",
                [
                    f"{summary['code_tests']['passed']}/{summary['code_tests']['evaluated']}"
                    for _, summary in entries
                ],
            ),
        ]
    )
    return rows


def render_markdown(entries: list[tuple[str, dict[str, Any]]]) -> str:
    """Render a compact Markdown comparison table."""

    headers = [label for label, _ in entries]
    lines = [
        "| Metric | " + " | ".join(headers) + " |",
        "|---|" + "---:|" * len(headers),
    ]
    for title, values in build_rows(entries):
        lines.append("| " + title + " | " + " | ".join(values) + " |")
    return "\n".join(lines)


def main() -> int:
    """CLI entry point for comparing two or more summary artifacts."""

    parser = argparse.ArgumentParser(
        description="Compare two or more benchmark summary.json files."
    )
    parser.add_argument("summaries", nargs="+", type=Path)
    args = parser.parse_args()

    if len(args.summaries) < 2:
        parser.error("Provide at least two summary.json files")

    entries: list[tuple[str, dict[str, Any]]] = []
    for path in args.summaries:
        metadata, summary = load_summary(path)
        entries.append((label_for(path, metadata), summary))

    print(render_markdown(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
