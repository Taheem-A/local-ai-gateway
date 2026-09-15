"""Index local text/Markdown/code/JSON/YAML/CSV/PDF files through the gateway API."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any, Iterable

import httpx
from dotenv import load_dotenv
from pypdf import PdfReader

SUPPORTED_TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".rst",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
}


def _stable_id(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def _iter_files(paths: list[Path], *, recursive: bool) -> Iterable[Path]:
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        candidates: Iterable[Path]
        if resolved.is_dir():
            candidates = resolved.rglob("*") if recursive else resolved.glob("*")
        else:
            candidates = (resolved,)
        for candidate in candidates:
            if not candidate.is_file() or candidate in seen:
                continue
            seen.add(candidate)
            yield candidate


def _documents_from_pdf(path: Path) -> list[dict[str, Any]]:
    """Represent each PDF page separately so citations retain page provenance."""

    reader = PdfReader(str(path))
    documents: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        source = f"{path}#page={page_number}"
        documents.append(
            {
                "id": _stable_id(source),
                "text": text,
                "source": source,
                "metadata": {
                    "path": str(path),
                    "extension": ".pdf",
                    "page": page_number,
                },
            }
        )
    return documents


def _documents_from_file(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        return _documents_from_pdf(path)
    if suffix not in SUPPORTED_TEXT_SUFFIXES:
        return []

    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    source = str(path)
    return [
        {
            "id": _stable_id(source),
            "text": text,
            "source": source,
            "metadata": {
                "path": source,
                "extension": suffix,
            },
        }
    ]


def _post_batch(
    *,
    base_url: str,
    api_key: str,
    project: str | None,
    collection: str,
    documents: list[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    headers = {"X-Local-AI-Key": api_key}
    if project:
        headers["X-Project-ID"] = project
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url.rstrip('/')}/v1/rag/index",
            headers=headers,
            json={"collection": collection, "documents": documents},
        )
    if not response.is_success:
        raise RuntimeError(
            f"Gateway returned {response.status_code}: {response.text}"
        )
    return response.json()


def main() -> int:
    """Parse CLI arguments, extract supported files, and submit bounded batches."""

    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", help="RAG collection name")
    parser.add_argument("paths", nargs="+", type=Path, help="Files or directories to index")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into directories",
    )
    parser.add_argument(
        "--gateway-url",
        default=os.getenv("LOCAL_AI_GATEWAY_URL", "http://127.0.0.1:4812"),
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("LOCAL_AI_GATEWAY_KEY") or os.getenv("GATEWAY_API_KEY"),
    )
    parser.add_argument("--project", default=None)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    if not args.api_key:
        parser.error("Set LOCAL_AI_GATEWAY_KEY/GATEWAY_API_KEY or pass --api-key")
    if args.batch_size < 1 or args.batch_size > 100:
        parser.error("--batch-size must be between 1 and 100")

    documents: list[dict[str, Any]] = []
    unsupported = 0
    for path in _iter_files(args.paths, recursive=args.recursive):
        extracted = _documents_from_file(path)
        if not extracted:
            unsupported += 1
            continue
        documents.extend(extracted)

    if not documents:
        print("No indexable text was found.")
        return 1

    total_chunks = 0
    for start in range(0, len(documents), args.batch_size):
        batch = documents[start : start + args.batch_size]
        result = _post_batch(
            base_url=args.gateway_url,
            api_key=args.api_key,
            project=args.project,
            collection=args.collection,
            documents=batch,
            timeout=args.timeout,
        )
        total_chunks += int(result["chunks"])
        print(
            f"Indexed {start + len(batch)}/{len(documents)} documents/pages "
            f"({result['chunks']} chunks in this batch)."
        )

    print(
        f"Done: {len(documents)} documents/pages, {total_chunks} chunks, "
        f"{unsupported} unsupported/empty files skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
