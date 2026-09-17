"""Run the frozen Stage 5 Vision core regression suite.

This entry point intentionally reuses the original deterministic fixture runner
so historical behavior stays comparable while the suite is clearly separated
from the realistic model-selection workload benchmark.
"""

from __future__ import annotations

from pathlib import Path

import run_vision_benchmarks as legacy

HERE = Path(__file__).resolve().parent
legacy.SUITE_PATH = HERE / "vision_core_suite.json"
legacy.RUNNER_PATH = Path(__file__).resolve()


if __name__ == "__main__":
    raise SystemExit(legacy.main())
