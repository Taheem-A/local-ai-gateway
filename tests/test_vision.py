"""Regression tests for Stage 5 image validation, model gating, and the public API."""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from app.config import settings
from app.main import app
from app.vision.errors import VisionInputError
from app.vision.images import prepare_vision_images
from app.vision.schemas import VisionImageInfo, VisionImageInput
from app.vision.service import VisionModelStatus, VisionResult, inspect_vision_model


def _png_bytes(width: int = 64, height: int = 48, *, metadata: bool = False) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    output = BytesIO()
    pnginfo = None
    if metadata:
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("secret-note", "must not survive normalization")
    image.save(output, format="PNG", pnginfo=pnginfo)
    return output.getvalue()


def _payload(raw: bytes, media_type: str = "image/png") -> VisionImageInput:
    return VisionImageInput(
        media_type=media_type,
        data_base64=base64.b64encode(raw).decode("ascii"),
    )


def _configure_temp_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_db_path", tmp_path / "gateway.db")
    monkeypatch.setattr(settings, "rag_db_path", tmp_path / "rag.db")
    monkeypatch.setattr(settings, "gateway_api_key", "vision-test-key")


def test_vision_preprocessing_resizes_and_strips_metadata(monkeypatch):
    monkeypatch.setattr(settings, "vision_max_side", 2048)
    prepared = prepare_vision_images([_payload(_png_bytes(4096, 1024, metadata=True))])

    assert len(prepared) == 1
    image = prepared[0]
    assert image.original_width == 4096
    assert image.original_height == 1024
    assert (image.width, image.height) == (2048, 512)

    normalized = base64.b64decode(image.data_url.split(",", 1)[1])
    with Image.open(BytesIO(normalized)) as decoded:
        assert "secret-note" not in decoded.info
        assert decoded.size == (2048, 512)


def test_vision_preprocessing_rejects_invalid_base64():
    with pytest.raises(VisionInputError, match="valid base64"):
        prepare_vision_images(
            [VisionImageInput(media_type="image/png", data_base64="not-base64!")]
        )


def test_vision_preprocessing_rejects_mime_spoofing():
    with pytest.raises(VisionInputError, match="media type did not match"):
        prepare_vision_images([_payload(_png_bytes(), "image/jpeg")])


def test_vision_preprocessing_enforces_total_batch_limit(monkeypatch):
    first = _png_bytes(128, 128)
    second = _png_bytes(128, 128)
    monkeypatch.setattr(settings, "vision_max_total_bytes", len(first) + len(second) - 1)

    with pytest.raises(VisionInputError, match="total byte limit"):
        prepare_vision_images([_payload(first), _payload(second)])


def test_vision_model_inventory_must_explicitly_advertise_vision(monkeypatch):
    monkeypatch.setattr(settings, "vision_model", "qwen/qwen3-vl-8b")
    models = [
        {
            "key": "qwen/qwen3-vl-8b",
            "capabilities": {"vision": True, "trained_for_tool_use": True},
            "loaded_instances": [{"id": "instance-1"}],
        }
    ]
    status = inspect_vision_model(models)
    assert status.installed is True
    assert status.supports_vision is True
    assert status.loaded is True

    unsupported = inspect_vision_model(
        [{"key": "qwen/qwen3-vl-8b", "capabilities": {"vision": False}}]
    )
    assert unsupported.installed is True
    assert unsupported.supports_vision is False


def test_vision_endpoint_returns_content_free_preprocessing_metadata(
    tmp_path, monkeypatch
):
    _configure_temp_storage(tmp_path, monkeypatch)

    async def fake_run_vision(_request):
        return VisionResult(
            text="The screenshot shows a connection error.",
            model="qwen/qwen3-vl-8b",
            images=[
                VisionImageInfo(
                    media_type="image/png",
                    original_width=1600,
                    original_height=900,
                    width=1600,
                    height=900,
                    input_bytes=1234,
                    processed_bytes=1100,
                )
            ],
            input_tokens=212,
            output_tokens=18,
            reasoning_output_tokens=0,
            tokens_per_second=42.0,
            time_to_first_token_seconds=0.4,
            model_load_time_seconds=None,
        )

    monkeypatch.setattr("app.vision.router.run_vision", fake_run_vision)
    body = {
        "prompt": "Explain this screenshot.",
        "images": [
            {
                "media_type": "image/png",
                "data_base64": base64.b64encode(_png_bytes()).decode("ascii"),
            }
        ],
    }
    with TestClient(app) as client:
        response = client.post(
            "/v1/vision",
            headers={
                "X-Local-AI-Key": "vision-test-key",
                "X-Project-ID": "vision-tests",
            },
            json=body,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"].startswith("The screenshot")
    assert payload["profile"] == "vision"
    assert payload["image_count"] == 1
    assert payload["images"][0]["width"] == 1600
    assert "data_base64" not in str(payload)


def test_vision_status_endpoint_reports_capability_without_loading(tmp_path, monkeypatch):
    _configure_temp_storage(tmp_path, monkeypatch)

    async def fake_status():
        return VisionModelStatus(
            model="qwen/qwen3-vl-8b",
            installed=True,
            supports_vision=True,
            loaded=False,
        )

    monkeypatch.setattr("app.vision.router.vision_model_status", fake_status)
    with TestClient(app) as client:
        response = client.get(
            "/v1/vision/status",
            headers={"X-Local-AI-Key": "vision-test-key"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "model": "qwen/qwen3-vl-8b",
        "installed": True,
        "supports_vision": True,
        "loaded": False,
    }
