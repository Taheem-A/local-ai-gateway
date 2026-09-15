"""Deterministic text chunking that prefers natural boundaries over hard cuts."""

from __future__ import annotations

import re

_BOUNDARIES = ("\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ")


def chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks while preserving useful local context.

    The chunker is intentionally tokenizer-independent so ingestion does not need
    to know which embedding backend is currently configured. Character limits are
    conservative relative to the supported embedding models' token windows.
    """

    if chunk_size < 200:
        raise ValueError("chunk_size must be at least 200 characters")
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    minimum_boundary = max(1, int(chunk_size * 0.6))

    while start < len(normalized):
        hard_end = min(start + chunk_size, len(normalized))
        end = hard_end

        if hard_end < len(normalized):
            search_floor = start + minimum_boundary
            best = -1
            best_width = 0
            for boundary in _BOUNDARIES:
                candidate = normalized.rfind(boundary, search_floor, hard_end)
                if candidate > best:
                    best = candidate
                    best_width = len(boundary)
            if best >= search_floor:
                end = best + best_width

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(normalized):
            break

        next_start = max(start + 1, end - overlap)
        # Avoid starting in the middle of a word when a nearby boundary exists.
        if next_start > 0 and not normalized[next_start - 1].isspace():
            whitespace = normalized.find(" ", next_start, min(end, next_start + 80))
            if whitespace != -1:
                next_start = whitespace + 1
        start = next_start

    return chunks
