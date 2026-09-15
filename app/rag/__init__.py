"""Retrieval-augmented generation helpers for the local gateway."""

from app.rag.service import (
    answer_with_rag,
    delete_collection,
    delete_document,
    embed_public_inputs,
    index_documents,
    list_collections,
    search_collection,
)
from app.rag.store import initialize_rag_db

__all__ = [
    "answer_with_rag",
    "delete_collection",
    "delete_document",
    "embed_public_inputs",
    "index_documents",
    "initialize_rag_db",
    "list_collections",
    "search_collection",
]
