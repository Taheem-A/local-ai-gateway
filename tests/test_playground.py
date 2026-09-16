"""Regression tests for the local playground shell and content-free debug APIs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.observability import RequestMetric, record_metric


def _configure_temp_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_db_path", tmp_path / "gateway.db")
    monkeypatch.setattr(settings, "rag_db_path", tmp_path / "rag.db")
    monkeypatch.setattr(settings, "gateway_api_key", "playground-test-key")


def test_playground_shell_is_secret_free_hardened_and_polished(tmp_path, monkeypatch):
    _configure_temp_storage(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response = client.get("/playground/")
        javascript = client.get("/playground/assets/app.js")
        ui_javascript = client.get("/playground/assets/ui.js")
        vision_javascript = client.get("/playground/assets/vision.js")
        stylesheet = client.get("/playground/assets/styles.css")
        polish_stylesheet = client.get("/playground/assets/polish.css")

    assert response.status_code == 200
    assert "Local AI Gateway Playground" in response.text
    assert 'data-theme="signal-red"' in response.text
    assert 'id="theme-select"' in response.text
    assert "/playground/assets/ui.js" in response.text
    assert "/playground/assets/vision.js" in response.text
    assert "/playground/assets/polish.css" in response.text
    assert "Ctrl K" in response.text
    assert 'aria-keyshortcuts="Control+K Meta+K"' in response.text
    assert 'aria-label="Refresh RAG collections"' in response.text
    assert "playground-test-key" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "blob:" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert javascript.status_code == 200
    assert ui_javascript.status_code == 200
    assert vision_javascript.status_code == 200
    assert stylesheet.status_code == 200
    assert polish_stylesheet.status_code == 200
    assert "/v1/vision" in vision_javascript.text
    assert 'data-view = "vision"' not in vision_javascript.text
    assert "Stage 5 accepts at most four images" in vision_javascript.text
    assert "#tools-form .form-actions" in polish_stylesheet.text
    assert ".vision-file-list" in polish_stylesheet.text
    assert "prefers-reduced-motion" in polish_stylesheet.text
    assert "focus-visible" in polish_stylesheet.text


def test_playground_exposes_all_dark_workbench_themes(tmp_path, monkeypatch):
    _configure_temp_storage(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response = client.get("/playground/")
        stylesheet = client.get("/playground/assets/styles.css")

    theme_ids = (
        "signal-red",
        "copper",
        "emerald",
        "cyan",
        "violet",
        "rose",
        "lime",
        "espresso",
    )
    for theme_id in theme_ids:
        assert f'value="{theme_id}"' in response.text
        assert f'data-theme="{theme_id}"' in stylesheet.text


def test_playground_only_serves_allowlisted_assets(tmp_path, monkeypatch):
    _configure_temp_storage(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response = client.get("/playground/assets/../router.py")

    assert response.status_code == 404


def test_debug_endpoints_require_gateway_key(tmp_path, monkeypatch):
    _configure_temp_storage(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response = client.get("/v1/debug/metrics")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"


def test_debug_requests_expose_metrics_but_no_content(tmp_path, monkeypatch):
    _configure_temp_storage(tmp_path, monkeypatch)
    record_metric(
        RequestMetric(
            request_id="req-123",
            project="playground",
            endpoint="/v1/generate",
            quality="default",
            model="openai/gpt-oss-20b",
            reasoning_level="low",
            input_tokens=20,
            reasoning_tokens=4,
            output_tokens=8,
            model_load_seconds=None,
            first_token_seconds=0.2,
            total_latency_seconds=0.8,
            attempts=1,
            success=True,
        )
    )

    headers = {"X-Local-AI-Key": "playground-test-key"}
    with TestClient(app) as client:
        metrics = client.get("/v1/debug/metrics?days=7", headers=headers)
        recent = client.get("/v1/debug/requests?limit=10", headers=headers)

    assert metrics.status_code == 200
    assert metrics.json()["requests"] == 1
    assert metrics.json()["success_rate_percent"] == 100.0

    assert recent.status_code == 200
    rows = recent.json()["requests"]
    assert len(rows) == 1
    assert rows[0]["request_id"] == "req-123"
    assert rows[0]["endpoint"] == "/v1/generate"
    assert rows[0]["success"] is True
    assert "prompt" not in rows[0]
    assert "response" not in rows[0]
    assert "tool_calls" not in rows[0]
    assert "rag_text" not in rows[0]
