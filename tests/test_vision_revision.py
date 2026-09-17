"""Regression coverage for the Stage 5 revision pass."""

from __future__ import annotations

import json
from pathlib import Path

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
from benchmarks.compare_vision_workloads import summarize_run
from benchmarks.run_vision_workload_benchmarks import PRIVATE_RESULTS_DIR, grade_text


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


def test_private_workload_results_default_outside_tracked_results():
    assert PRIVATE_RESULTS_DIR.name == "private-results"
    assert PRIVATE_RESULTS_DIR.parent.name == "benchmarks"


def test_workload_comparator_requires_manual_review_and_no_blockers(tmp_path: Path):
    run = tmp_path / "candidate"
    run.mkdir()
    (run / "summary.json").write_text(
        json.dumps(
            {
                "pipeline": "direct",
                "vision_models": ["example/vlm"],
                "reason_models": [],
                "cases": 1,
                "request_errors": 0,
                "automatic_case_accuracy_percent": 100.0,
                "mean_latency_seconds": 2.0,
                "suite_sha256": "suite",
                "runner_sha256": "runner",
            }
        ),
        encoding="utf-8",
    )
    (run / "manual_review.json").write_text(
        json.dumps(
            {
                "scores": [
                    {
                        "id": "case",
                        "ocr_text_fidelity_0_2": 2,
                        "visual_spatial_accuracy_0_2": 2,
                        "reasoning_quality_0_2": 2,
                        "unsupported_claim_discipline_0_2": 2,
                        "instruction_following_0_2": 2,
                        "multi_image_correctness_0_2": None,
                        "production_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = summarize_run(run)
    assert result["manual_review_complete"] is True
    assert result["selection_eligible"] is True
    assert result["manual_dimension_means"]["visual_spatial_accuracy_0_2"] == 2.0


def test_playground_mounts_local_markdown_and_shared_prose_renderers():
    with TestClient(app) as client:
        response = client.get("/playground/")
        markdown = client.get("/playground/assets/markdown.js")
        prose = client.get("/playground/assets/prose.js")

    assert response.status_code == 200
    assert '/playground/assets/markdown.js' in response.text
    assert '/playground/assets/prose.js' in response.text
    assert markdown.status_code == 200
    assert prose.status_code == 200
    assert "innerHTML" not in markdown.text
    assert "createTextNode" in markdown.text
    assert "PlaygroundMarkdown" in prose.text
    assert "rag-answer" in prose.text
    assert "tools-prose" in prose.text
