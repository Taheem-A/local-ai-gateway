"""Benchmark live RAG retrieval quality and latency through the gateway API."""

from __future__ import annotations

import argparse
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
SUITE_PATH = BENCH_DIR / "rag_suite.json"


def _headers(api_key: str, project: str) -> dict[str, str]:
    return {"X-Local-AI-Key": api_key, "X-Project-ID": project}


def _post(
    client: httpx.Client,
    base_url: str,
    path: str,
    headers: dict[str, str],
    body: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(f"{base_url}{path}", headers=headers, json=body)
    if not response.is_success:
        raise RuntimeError(f"{path} returned {response.status_code}: {response.text}")
    return response.json()


def main() -> int:
    """Index a fixed corpus, measure retrieval ranks, save artifacts, and clean up."""

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
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--keep-collection", action="store_true")
    parser.add_argument("--name", default="rag-retrieval-v1")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("Set LOCAL_AI_GATEWAY_KEY/GATEWAY_API_KEY or pass --api-key")
    if args.top_k < 1 or args.top_k > 50:
        parser.error("--top-k must be between 1 and 50")

    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    collection = f"bench-{uuid.uuid4().hex[:12]}"
    base_url = args.gateway_url.rstrip("/")
    headers = _headers(args.api_key, "rag-benchmark")
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()

    with httpx.Client(timeout=300.0) as client:
        _post(
            client,
            base_url,
            "/v1/rag/index",
            headers,
            {"collection": collection, "documents": suite["documents"]},
        )

        try:
            for case in suite["queries"]:
                case_started = time.perf_counter()
                result = _post(
                    client,
                    base_url,
                    "/v1/rag/search",
                    headers,
                    {
                        "collection": collection,
                        "query": case["query"],
                        "top_k": args.top_k,
                    },
                )
                latency = time.perf_counter() - case_started
                ids = [hit["document_id"] for hit in result["hits"]]
                expected = case["expected_document_id"]
                rank = ids.index(expected) + 1 if expected in ids else None
                rows.append(
                    {
                        "id": case["id"],
                        "query": case["query"],
                        "expected_document_id": expected,
                        "rank": rank,
                        "latency_seconds": latency,
                        "hits": result["hits"],
                    }
                )
                print(f"{case['id']}: rank={rank} latency={latency:.3f}s")
        finally:
            if not args.keep_collection:
                response = client.delete(
                    f"{base_url}/v1/rag/collections/{collection}",
                    headers=headers,
                )
                response.raise_for_status()

    latencies = [row["latency_seconds"] for row in rows]
    total = len(rows)

    def recall_at(k: int) -> float:
        passed = sum(row["rank"] is not None and row["rank"] <= k for row in rows)
        return 100.0 * passed / total if total else 0.0

    reciprocal_ranks = [1.0 / row["rank"] if row["rank"] else 0.0 for row in rows]
    summary = {
        "suite_version": suite["version"],
        "cases": total,
        "recall_at_1_percent": round(recall_at(1), 2),
        "recall_at_3_percent": round(recall_at(3), 2),
        "recall_at_5_percent": round(recall_at(5), 2),
        "mean_reciprocal_rank": round(statistics.mean(reciprocal_ranks), 4),
        "mean_latency_seconds": round(statistics.mean(latencies), 4),
        "median_latency_seconds": round(statistics.median(latencies), 4),
        "total_seconds": round(time.perf_counter() - started, 3),
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = RESULTS_DIR / f"{timestamp}_{args.name}_{uuid.uuid4().hex[:6]}"
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "raw_results.json").write_text(
        json.dumps({"summary": summary, "results": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    report = [
        "# RAG retrieval benchmark",
        "",
        f"- Cases: {total}",
        f"- Recall@1: {summary['recall_at_1_percent']:.2f}%",
        f"- Recall@3: {summary['recall_at_3_percent']:.2f}%",
        f"- Recall@5: {summary['recall_at_5_percent']:.2f}%",
        f"- MRR: {summary['mean_reciprocal_rank']:.4f}",
        f"- Mean latency: {summary['mean_latency_seconds']:.4f}s",
        f"- Median latency: {summary['median_latency_seconds']:.4f}s",
        "",
        "| Case | Expected document | Rank | Latency (s) |",
        "|---|---|---:|---:|",
    ]
    for row in rows:
        report.append(
            f"| {row['id']} | {row['expected_document_id']} | "
            f"{row['rank'] or '-'} | {row['latency_seconds']:.4f} |"
        )
    (output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Saved to {output_dir}")
    return 0 if summary["recall_at_5_percent"] == 100.0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
