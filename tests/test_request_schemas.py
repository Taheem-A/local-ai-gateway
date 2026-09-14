import pytest
from pydantic import ValidationError

from app.schemas import ClassifyRequest


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
