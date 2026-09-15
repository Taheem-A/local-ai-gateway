"""SQLite persistence and dense cosine retrieval for RAG chunks."""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


@dataclass(frozen=True)
class StoredChunk:
    """One persisted text chunk and its normalized embedding vector."""

    collection: str
    document_id: str
    chunk_index: int
    source: str | None
    text: str
    metadata: dict[str, Any]
    embedding_model: str
    embedding: list[float]


@dataclass(frozen=True)
class SearchResult:
    """One retrieval hit ordered by cosine similarity."""

    document_id: str
    chunk_index: int
    source: str | None
    text: str
    metadata: dict[str, Any]
    score: float


def _db_path() -> Path:
    path = settings.rag_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def initialize_rag_db() -> None:
    """Create the durable RAG schema and supporting indexes."""

    with sqlite3.connect(_db_path()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_chunks (
                collection TEXT NOT NULL,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                source TEXT,
                text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dim INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (collection, document_id, chunk_index)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_collection "
            "ON rag_chunks(collection)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_model "
            "ON rag_chunks(collection, embedding_model, embedding_dim)"
        )
        connection.commit()


def unit_vector(vector: list[float]) -> list[float]:
    """Return a normalized vector suitable for cosine similarity via dot product."""

    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("embedding vector has zero or non-finite magnitude")
    result = [float(value / norm) for value in vector]
    if any(not math.isfinite(value) for value in result):
        raise ValueError("embedding vector contains non-finite values")
    return result


def _pack_embedding(vector: list[float]) -> bytes:
    if not vector:
        raise ValueError("embedding vector cannot be empty")
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack_embedding(blob: bytes, dimension: int) -> tuple[float, ...]:
    expected_size = 4 * dimension
    if len(blob) != expected_size:
        raise ValueError("stored embedding byte length does not match its dimension")
    return struct.unpack(f"<{dimension}f", blob)


def collection_signature(collection: str) -> tuple[str, int] | None:
    """Return the single model/dimension signature used by a collection."""

    initialize_rag_db()
    with sqlite3.connect(_db_path()) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT embedding_model, embedding_dim
            FROM rag_chunks
            WHERE collection = ?
            """,
            (collection,),
        ).fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError("collection contains mixed embedding models or dimensions")
    return str(rows[0][0]), int(rows[0][1])


def replace_document(
    *,
    collection: str,
    document_id: str,
    source: str | None,
    metadata: dict[str, Any],
    chunks: list[tuple[int, str, str, str, list[float]]],
) -> None:
    """Atomically replace all chunks belonging to one document.

    Each chunk tuple is `(index, text, content_hash, model, embedding)`. Embeddings
    are expected to be normalized before storage.
    """

    initialize_rag_db()
    timestamp = datetime.now(timezone.utc).isoformat()
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)

    with sqlite3.connect(_db_path()) as connection:
        connection.execute("BEGIN")
        connection.execute(
            "DELETE FROM rag_chunks WHERE collection = ? AND document_id = ?",
            (collection, document_id),
        )
        for index, text, content_hash, model, embedding in chunks:
            connection.execute(
                """
                INSERT INTO rag_chunks (
                    collection, document_id, chunk_index, source, text,
                    metadata_json, content_hash, embedding_model, embedding_dim,
                    embedding, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    collection,
                    document_id,
                    index,
                    source,
                    text,
                    metadata_json,
                    content_hash,
                    model,
                    len(embedding),
                    _pack_embedding(embedding),
                    timestamp,
                ),
            )
        connection.commit()


def search(
    *,
    collection: str,
    query_embedding: list[float],
    embedding_model: str,
    top_k: int,
    min_score: float,
    metadata_filter: dict[str, Any] | None = None,
) -> list[SearchResult]:
    """Return the highest-cosine chunks from one compatible collection."""

    initialize_rag_db()
    query = unit_vector(query_embedding)
    dimension = len(query)

    with sqlite3.connect(_db_path()) as connection:
        rows = connection.execute(
            """
            SELECT document_id, chunk_index, source, text, metadata_json,
                   embedding_dim, embedding
            FROM rag_chunks
            WHERE collection = ? AND embedding_model = ? AND embedding_dim = ?
            """,
            (collection, embedding_model, dimension),
        ).fetchall()

    scored: list[SearchResult] = []
    for row in rows:
        metadata = json.loads(row[4])
        if metadata_filter and any(
            metadata.get(key) != value for key, value in metadata_filter.items()
        ):
            continue

        stored = _unpack_embedding(row[6], int(row[5]))
        score = float(sum(left * right for left, right in zip(query, stored)))
        if score < min_score:
            continue
        scored.append(
            SearchResult(
                document_id=str(row[0]),
                chunk_index=int(row[1]),
                source=str(row[2]) if row[2] is not None else None,
                text=str(row[3]),
                metadata=metadata,
                score=score,
            )
        )

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def list_collections() -> list[dict[str, Any]]:
    """Return chunk/document counts and embedding signatures for all collections."""

    initialize_rag_db()
    with sqlite3.connect(_db_path()) as connection:
        rows = connection.execute(
            """
            SELECT collection,
                   COUNT(*) AS chunks,
                   COUNT(DISTINCT document_id) AS documents,
                   MIN(embedding_model) AS embedding_model,
                   MIN(embedding_dim) AS embedding_dim
            FROM rag_chunks
            GROUP BY collection
            ORDER BY collection
            """
        ).fetchall()
    return [
        {
            "collection": str(row[0]),
            "chunks": int(row[1]),
            "documents": int(row[2]),
            "embedding_model": str(row[3]),
            "embedding_dim": int(row[4]),
        }
        for row in rows
    ]


def delete_collection(collection: str) -> int:
    """Delete a collection and return the number of removed chunks."""

    initialize_rag_db()
    with sqlite3.connect(_db_path()) as connection:
        cursor = connection.execute(
            "DELETE FROM rag_chunks WHERE collection = ?",
            (collection,),
        )
        connection.commit()
        return int(cursor.rowcount)


def delete_document(collection: str, document_id: str) -> int:
    """Delete one document from a collection and return removed chunk count."""

    initialize_rag_db()
    with sqlite3.connect(_db_path()) as connection:
        cursor = connection.execute(
            "DELETE FROM rag_chunks WHERE collection = ? AND document_id = ?",
            (collection, document_id),
        )
        connection.commit()
        return int(cursor.rowcount)
