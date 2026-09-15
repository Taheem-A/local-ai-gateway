"""Request-schema regression tests for classification, embeddings, and RAG."""

import pytest
from pydantic import ValidationError

from app.schemas import ClassifyRequest, EmbeddingRequest, RagIndexRequest, RagSearchRequest


def test_classification_default_budget_leaves_room_for_reasoning():
    request = ClassifyRequest(
        text="Homework 4 is due Sunday.",
        labels=["assignment", "exam"],
    )
    assert request.max_output_tokens == 512


def test_classification_rejects_dangerously_tiny_budget():
    with pytest.raises(ValidationError):
        ClassifyRequest(
            text="Homework 4 is due Sunday.",
            labels=["assignment", "exam"],
            max_output_tokens=64,
        )


def test_embeddings_reject_empty_batches_and_blank_text():
    with pytest.raises(ValidationError):
        EmbeddingRequest(input=[])
    with pytest.raises(ValidationError):
        EmbeddingRequest(input=["valid", "   "])


def test_rag_collection_names_are_filesystem_and_url_safe():
    RagSearchRequest(collection="uoft-notes_2026", query="turnbuckles")
    with pytest.raises(ValidationError):
        RagSearchRequest(collection="../../private", query="turnbuckles")


def test_rag_index_rejects_overlap_not_smaller_than_chunk():
    with pytest.raises(ValidationError):
        RagIndexRequest(
            collection="notes",
            documents=[{"id": "one", "text": "x" * 500}],
            chunk_size_chars=300,
            chunk_overlap_chars=300,
        )
