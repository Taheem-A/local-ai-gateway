"""Regression coverage for the Stage 5 revision pass."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.vision.errors import (
    VisionProviderRejectedError,
    VisionProviderUnavailableError,
    VisionRuntimeError,
)
from app.vision.provider import _raise_for_provider_failure
from benchmarks.run_vision_workload_benchmarks import grade_text


def _response(status: int, payload: dict) -> httpx.Response:
    request = httpx.Request("POST", "http://127.0.0.1:1234/api/v1/chat")
    return httpx.Response(status, json=payload, request=request)


def test_gemma_terminated_error_includes_physical_batch_advisory(monkeypatch):
    monkeypatch.setattr(settings, "vision_model", "google/gemma-4-12b-qat")
    response = _response(
        500,
        {"error": {"message": "terminated", "type": "internal_error", "code": "unknown"}},
    )

    with pytest.raises(VisionRuntimeError) as caught:
        _raise_for_provider_failure(response)

    assert caught.value.code == "VISION_RUNTIME_FAILED"
    assert caught.value.details["retryable"] is True
    assert caught.value.details["advisory"]["id"] == "gemma4-physical-batch"
    assert "2048" in caught.value.details["advisory"]["suggested_action"]


def test_provider_busy_and_rejected_are_distinct():
    with pytest.raises(VisionProviderUnavailableError) as busy:
        _raise_for_provider_failure(_response(429, {"error": {"message": "busy"}}))
    assert busy.value.code == "VISION_PROVIDER_UNAVAILABLE"

    with pytest.raises(VisionProviderRejectedError) as rejected:
        _raise_for_provider_failure(_response(422, {"error": {"message": "bad request"}}))
    assert rejected.value.code == "VISION_PROVIDER_REJECTED"


def test_workload_grader_checks_expected_and_forbidden_claims():
    passed = grade_text(
        "The dialog visibly says E_CONN_4812 and DISCONNECTED.",
        ["E_CONN_4812", "DISCONNECTED"],
        ["ACCESS_DENIED"],
    )
    assert passed["automatic_pass"] is True

    failed = grade_text(
        "The dialog says E_CONN_4812 but also ACCESS_DENIED.",
        ["E_CONN_4812", "DISCONNECTED"],
        ["ACCESS_DENIED"],
    )
    assert failed["automatic_pass"] is False
    assert failed["missing_terms"] == ["DISCONNECTED"]
    assert failed["forbidden_hits"] == ["ACCESS_DENIED"]


def test_playground_mounts_local_markdown_renderer():
    with TestClient(app) as client:
        response = client.get("/playground/")
        asset = client.get("/playground/assets/markdown.js")

    assert response.status_code == 200
    assert '/playground/assets/markdown.js' in response.text
    assert asset.status_code == 200
    assert "innerHTML" not in asset.text
    assert "createTextNode" in asset.text
