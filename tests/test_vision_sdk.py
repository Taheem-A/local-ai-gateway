"""Tests for Stage 5 SDK image encoding and public vision methods."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from taheem_ai import AI, AsyncAI
from taheem_ai.vision import encode_vision_images


def _image_bytes(fmt: str) -> bytes:
    image = Image.new("RGB", (32, 24), "white")
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


def test_encode_vision_images_detects_supported_formats(tmp_path):
    png = tmp_path / "sample.png"
    png.write_bytes(_image_bytes("PNG"))
    encoded = encode_vision_images([png, _image_bytes("JPEG"), _image_bytes("WEBP")])

    assert [item["media_type"] for item in encoded] == [
        "image/png",
        "image/jpeg",
        "image/webp",
    ]
    assert all(item["data_base64"] for item in encoded)


def test_encode_vision_images_rejects_unknown_bytes():
    with pytest.raises(ValueError, match="PNG, JPEG, or WebP"):
        encode_vision_images(b"definitely-not-an-image")


def test_public_sync_client_exposes_vision(monkeypatch):
    client = AI(api_key="sdk-test")
    captured = {}

    def fake_request(method, path, **kwargs):
        captured.update({"method": method, "path": path, **kwargs})
        return {"text": "I can see it."}

    monkeypatch.setattr(client, "_request", fake_request)
    text = client.vision(
        _image_bytes("PNG"),
        "What is shown?",
        max_output_tokens=300,
    )

    assert text == "I can see it."
    assert captured["path"] == "/v1/vision"
    assert captured["json"]["prompt"] == "What is shown?"
    assert captured["json"]["images"][0]["media_type"] == "image/png"
    assert captured["json"]["max_output_tokens"] == 300


@pytest.mark.anyio
async def test_public_async_client_exposes_vision(monkeypatch):
    client = AsyncAI(api_key="sdk-test")
    captured = {}

    async def fake_request(method, path, **kwargs):
        captured.update({"method": method, "path": path, **kwargs})
        return {"text": "Async vision works."}

    monkeypatch.setattr(client, "_request", fake_request)
    text = await client.vision(_image_bytes("WEBP"), "Describe it.")

    assert text == "Async vision works."
    assert captured["path"] == "/v1/vision"
    assert captured["json"]["images"][0]["media_type"] == "image/webp"
