"""Image encoding helpers and public SDK mixins for Stage 5 vision."""

from __future__ import annotations

import base64
from collections.abc import Iterable
from os import PathLike
from pathlib import Path
from typing import Any, TypeAlias

VisionImageSource: TypeAlias = str | PathLike[str] | bytes | bytearray | memoryview


def _media_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Vision images must be PNG, JPEG, or WebP.")


def _read_image(source: VisionImageSource) -> bytes:
    if isinstance(source, (str, PathLike)):
        path = Path(source)
        if not path.is_file():
            raise ValueError(f"Vision image does not exist or is not a file: {path}")
        data = path.read_bytes()
    else:
        data = bytes(source)
    if not data:
        raise ValueError("Vision image cannot be empty.")
    return data


def encode_vision_images(
    images: VisionImageSource | Iterable[VisionImageSource],
) -> list[dict[str, str]]:
    """Convert local paths/bytes into the gateway's explicit base64 image shape."""

    if isinstance(images, (str, PathLike, bytes, bytearray, memoryview)):
        sources = [images]
    else:
        sources = list(images)
    if not sources:
        raise ValueError("At least one vision image is required.")

    encoded: list[dict[str, str]] = []
    for source in sources:
        data = _read_image(source)
        encoded.append(
            {
                "media_type": _media_type(data),
                "data_base64": base64.b64encode(data).decode("ascii"),
            }
        )
    return encoded


class VisionSyncMixin:
    """Synchronous vision methods composed into the public `AI` client."""

    def vision_response(
        self,
        image: VisionImageSource | Iterable[VisionImageSource],
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_output_tokens: int = 2048,
    ) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "images": encode_vision_images(image),
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if system is not None:
            payload["system"] = system
        return self._request("POST", "/v1/vision", json=payload)  # type: ignore[attr-defined]

    def vision(
        self,
        image: VisionImageSource | Iterable[VisionImageSource],
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_output_tokens: int = 2048,
    ) -> str:
        """Analyze one or more local images and return visible model text."""

        result = self.vision_response(
            image,
            prompt,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        return str(result["text"])


class VisionAsyncMixin:
    """Asynchronous vision methods composed into the public `AsyncAI` client."""

    async def vision_response(
        self,
        image: VisionImageSource | Iterable[VisionImageSource],
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_output_tokens: int = 2048,
    ) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "images": encode_vision_images(image),
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if system is not None:
            payload["system"] = system
        return await self._request("POST", "/v1/vision", json=payload)  # type: ignore[attr-defined]

    async def vision(
        self,
        image: VisionImageSource | Iterable[VisionImageSource],
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_output_tokens: int = 2048,
    ) -> str:
        """Analyze images asynchronously and return visible model text."""

        result = await self.vision_response(
            image,
            prompt,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        return str(result["text"])
