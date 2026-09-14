"""Run the current benchmark suite sequentially against the local gateway."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from grading import grade
from reporting import make_summary, save_results

BENCH_DIR = Path(__file__).resolve().parent
ROOT = BENCH_DIR.parent
RESULTS_DIR = BENCH_DIR / "results"
CURRENT_SUITE_PATH = BENCH_DIR / "current_suite.json"


def load_env(path: Path) -> None:
    """Load simple KEY=value entries without replacing existing environment values."""

    if not path.exists():
        return

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_suite_policy() -> dict[str, Any]:
    """Load the versioned policy layered over the frozen v2 case definitions."""

    if not CURRENT_SUITE_PATH.exists():
        raise ValueError(f"Missing current benchmark policy: {CURRENT_SUITE_PATH}")
    return json.loads(CURRENT_SUITE_PATH.read_text(encoding="utf-8"))


def load_cases() -> list[dict[str, Any]]:
    """Load frozen base cases and apply the current suite's explicit overrides."""

    policy = load_suite_policy()
    overrides = policy.get("overrides", {})
    policy_defaults = policy.get("defaults", {})

    cases: list[dict[str, Any]] = []
    seen: set[str] = set()

    for path in sorted(BENCH_DIR.glob("cases_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        defaults = {**data.get("defaults", {}), **policy_defaults}

        for base_case in data["cases"]:
            case_id = base_case["id"]
            if case_id in seen:
                raise ValueError(f"Duplicate benchmark ID: {case_id}")
            seen.add(case_id)

            override = overrides.get(case_id, {})
            case = {**base_case, **override}
            case.update(
                _suite=data.get("suite", path.stem),
                _source=path.name,
                _defaults=defaults,
            )
            cases.append(case)

    unknown_overrides = sorted(set(overrides) - seen)
    if unknown_overrides:
        raise ValueError(f"Overrides reference unknown case IDs: {unknown_overrides}")
    if not cases:
        raise ValueError("No benchmark cases found")
    return cases


def now() -> str:
    """Return the current local timestamp with timezone information."""

    return datetime.now().astimezone().isoformat()


def error_grade(reason: str) -> dict[str, Any]:
    """Create the standard grading record for a request/runtime error."""

    return {
        "version": load_suite_policy()["version"],
        "status": "error",
        "passed": None,
        "semantic_correct": None,
        "format_correct": None,
        "instruction_following": None,
        "reason": reason,
    }


def benchmark_source_hashes() -> dict[str, str]:
    """Hash source files needed to reproduce the benchmark and gateway behavior."""

    sources = list(BENCH_DIR.glob("cases_*.json"))
    sources.append(CURRENT_SUITE_PATH)
    sources.extend(BENCH_DIR.glob("*.py"))
    sources.extend((ROOT / "app").rglob("*.py"))

    unique_sources = sorted({path.resolve() for path in sources if path.is_file()})
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in unique_sources
    }


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface for live runs and offline regrades."""

    parser = argparse.ArgumentParser(
        description="Sequential benchmark with independent semantic/format/instruction scores."
    )
    parser.add_argument("--quality", choices=["fast", "balanced", "default", "deep"])
    parser.add_argument(
        "--reasoning",
        choices=["low", "medium", "high"],
        help="Explicit reasoning-effort override for controlled comparisons.",
    )
    parser.add_argument("--name")
    parser.add_argument("--category")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        choices=range(1, 8193),
        metavar="1..8192",
        help="Override the total generation budget equally across selected cases.",
    )
    parser.add_argument("--skip-code-tests", action="store_true")
    parser.add_argument(
        "--regrade",
        type=Path,
        help="Regrade a saved raw/partial_results.json without sending model requests.",
    )
    return parser


def _regrade(
    *,
    source_path: Path,
    cases: list[dict[str, Any]],
    run_dir: Path,
    metadata: dict[str, Any],
    execute_code: bool,
) -> int:
    """Regrade historical responses into a new run without mutating the source run."""

    previous = json.loads(source_path.read_text(encoding="utf-8"))
    lookup = {case["id"]: case for case in cases}
    selected = [row for row in previous["results"] if row["id"] in lookup]

    prompts_unchanged = all(
        row.get("prompt", lookup[row["id"]]["prompt"]) == lookup[row["id"]]["prompt"]
        for row in selected
    )
    metadata.update(
        source_run=str(source_path.resolve()),
        source_metadata=previous.get("metadata"),
        case_count=len(selected),
        historical_prompts_unchanged=prompts_unchanged,
    )

    results: list[dict[str, Any]] = []
    for old in selected:
        case = lookup[old["id"]]
        row = {
            **old,
            "original_grade": old["grade"],
            "prompt": old.get("prompt", case["prompt"]),
            "expected": case["expected"],
        }
        if old["grade"]["status"] == "error":
            row["grade"] = error_grade(old.get("error") or "Original request failed")
        else:
            row["grade"] = grade(
                case,
                old.get("response", {}).get("text", ""),
                execute_code,
            )
        results.append(row)
        save_results(run_dir, metadata, results)

    metadata["state"] = "completed"
    metadata["finished_at"] = now()
    save_results(run_dir, metadata, results)
    print(f"Regraded {len(results)} cases. Original run preserved.\nResults: {run_dir}")
    return 0


def main() -> int:
    """Run or regrade the current benchmark suite."""

    parser = build_parser()
    args = parser.parse_args()
    policy = load_suite_policy()
    cases = load_cases()

    if args.category:
        cases = [case for case in cases if case["category"] == args.category]
    if not cases:
        parser.error("No cases match this category")

    label = re.sub(r"[^A-Za-z0-9._-]+", "_", args.name or args.quality or "benchmark")
    run_dir = RESULTS_DIR / (
        f"{datetime.now():%Y%m%d_%H%M%S_%f}_{label}_{uuid.uuid4().hex[:6]}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    metadata: dict[str, Any] = {
        "version": policy["version"],
        "started_at": now(),
        "forced_quality": args.quality,
        "forced_reasoning": args.reasoning,
        "name": args.name,
        "case_count": len(cases),
        "state": "running",
        "execute_code": not args.skip_code_tests,
        "max_output_tokens_override": args.max_output_tokens,
        "source_sha256": benchmark_source_hashes(),
    }

    if args.regrade:
        return _regrade(
            source_path=args.regrade,
            cases=cases,
            run_dir=run_dir,
            metadata=metadata,
            execute_code=not args.skip_code_tests,
        )

    load_env(ROOT / ".env")
    api_key = os.getenv("GATEWAY_API_KEY") or os.getenv("LOCAL_AI_GATEWAY_KEY")
    if not api_key:
        print("GATEWAY_API_KEY was not found in .env.", file=sys.stderr)
        return 2

    gateway = os.getenv("LOCAL_AI_GATEWAY_URL", "http://127.0.0.1:4812").rstrip("/")
    results: list[dict[str, Any]] = []
    save_results(run_dir, metadata, results)
    exit_code = 0

    try:
        with httpx.Client(timeout=300) as client:
            client.get(f"{gateway}/health").raise_for_status()

            for number, case in enumerate(cases, 1):
                defaults = case["_defaults"]
                quality = args.quality or case.get("quality") or defaults.get("quality", "default")
                body: dict[str, Any] = {
                    "prompt": case["prompt"],
                    "quality": quality,
                    "temperature": case.get(
                        "temperature", defaults.get("temperature", 0.0)
                    ),
                    "max_output_tokens": args.max_output_tokens
                    or case.get("max_output_tokens", 2048),
                }
                if args.reasoning:
                    body["reasoning"] = args.reasoning
                if case.get("system"):
                    body["system"] = case["system"]

                row: dict[str, Any] = {
                    "id": case["id"],
                    "suite": case["_suite"],
                    "source_file": case["_source"],
                    "category": case["category"],
                    "difficulty": case["difficulty"],
                    "quality": quality,
                    "reasoning": args.reasoning,
                    "prompt": case["prompt"],
                    "expected": case["expected"],
                    "request": body,
                    "response": {},
                    "grade": {},
                    "error": None,
                    "wall_time_seconds": None,
                }

                reasoning_suffix = f", reasoning={args.reasoning}" if args.reasoning else ""
                print(
                    f"[{number:02d}/{len(cases):02d}] {case['id']} "
                    f"({quality}{reasoning_suffix})",
                    end=" ... ",
                    flush=True,
                )
                start = time.perf_counter()

                try:
                    response = client.post(
                        f"{gateway}/v1/generate",
                        headers={"X-Local-AI-Key": api_key},
                        json=body,
                    )
                    row["wall_time_seconds"] = round(time.perf_counter() - start, 3)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
                        raise ValueError("Gateway response must contain a string text field")
                    row["response"] = data
                    row["grade"] = grade(case, data["text"], not args.skip_code_tests)
                except KeyboardInterrupt:
                    row["error"] = "Interrupted during case"
                    row["grade"] = error_grade(row["error"])
                    raise
                except Exception as error:
                    row["error"] = str(error)
                    row["grade"] = error_grade(row["error"])
                finally:
                    if row["wall_time_seconds"] is None:
                        row["wall_time_seconds"] = round(time.perf_counter() - start, 3)
                    results.append(row)
                    save_results(run_dir, metadata, results)

                print(str(row["grade"].get("status", "")).upper())

        metadata["state"] = "completed"
    except KeyboardInterrupt:
        metadata["state"] = "interrupted"
        exit_code = 130
    except Exception as error:
        metadata.update(state="error", error=str(error))
        print(f"Benchmark stopped: {error}", file=sys.stderr)
        exit_code = 3
    finally:
        metadata["finished_at"] = now()
        save_results(run_dir, metadata, results)

    summary: dict[str, Any] = make_summary(results)
    for key, score in summary["scores"].items():
        print(f"{key}: {score['passed']}/{score['evaluated']} ({score['percent']}%)")
    print(f"Results: {run_dir}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
