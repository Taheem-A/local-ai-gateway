from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


@dataclass
class RequestMetric:
    request_id: str
    project: str | None
    endpoint: str
    quality: str
    model: str | None
    reasoning_level: str | None
    input_tokens: int | None
    reasoning_tokens: int | None
    output_tokens: int | None
    model_load_seconds: float | None
    first_token_seconds: float | None
    total_latency_seconds: float
    attempts: int
    success: bool
    error_code: str | None = None


def _db_path() -> Path:
    path = settings.metrics_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def initialize_metrics_db() -> None:
    with sqlite3.connect(_db_path()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                project TEXT,
                endpoint TEXT NOT NULL,
                quality TEXT NOT NULL,
                model TEXT,
                reasoning_level TEXT,
                input_tokens INTEGER,
                reasoning_tokens INTEGER,
                output_tokens INTEGER,
                model_load_seconds REAL,
                first_token_seconds REAL,
                total_latency_seconds REAL NOT NULL,
                attempts INTEGER NOT NULL,
                success INTEGER NOT NULL,
                error_code TEXT
            )
            """
        )
        connection.commit()


def record_metric(metric: RequestMetric) -> None:
    initialize_metrics_db()
    with sqlite3.connect(_db_path()) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO requests (
                request_id, timestamp, project, endpoint, quality, model,
                reasoning_level, input_tokens, reasoning_tokens, output_tokens,
                model_load_seconds, first_token_seconds, total_latency_seconds,
                attempts, success, error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric.request_id,
                datetime.now(timezone.utc).isoformat(),
                metric.project,
                metric.endpoint,
                metric.quality,
                metric.model,
                metric.reasoning_level,
                metric.input_tokens,
                metric.reasoning_tokens,
                metric.output_tokens,
                metric.model_load_seconds,
                metric.first_token_seconds,
                metric.total_latency_seconds,
                metric.attempts,
                1 if metric.success else 0,
                metric.error_code,
            ),
        )
        connection.commit()


def summary(days: int = 30) -> dict[str, Any]:
    initialize_metrics_db()
    modifier = f"-{int(days)} days"
    with sqlite3.connect(_db_path()) as connection:
        connection.row_factory = sqlite3.Row
        aggregate = connection.execute(
            """
            SELECT
                COUNT(*) AS requests,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes,
                AVG(total_latency_seconds) AS mean_latency,
                SUM(COALESCE(input_tokens, 0)) AS input_tokens,
                SUM(COALESCE(output_tokens, 0)) AS output_tokens,
                SUM(COALESCE(reasoning_tokens, 0)) AS reasoning_tokens
            FROM requests
            WHERE timestamp >= datetime('now', ?)
            """,
            (modifier,),
        ).fetchone()

        by_quality = connection.execute(
            """
            SELECT quality, COUNT(*) AS count
            FROM requests
            WHERE timestamp >= datetime('now', ?)
            GROUP BY quality
            ORDER BY count DESC
            """,
            (modifier,),
        ).fetchall()

    request_count = int(aggregate["requests"] or 0)
    successes = int(aggregate["successes"] or 0)
    return {
        "days": days,
        "requests": request_count,
        "successes": successes,
        "success_rate_percent": round(100 * successes / request_count, 2)
        if request_count
        else None,
        "mean_latency_seconds": round(float(aggregate["mean_latency"]), 3)
        if aggregate["mean_latency"] is not None
        else None,
        "input_tokens": int(aggregate["input_tokens"] or 0),
        "output_tokens": int(aggregate["output_tokens"] or 0),
        "reasoning_tokens": int(aggregate["reasoning_tokens"] or 0),
        "by_quality": {row["quality"]: row["count"] for row in by_quality},
    }
