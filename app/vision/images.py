"""Decode, verify, normalize, and bound image inputs before local inference."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.vision.errors import VisionInputError
from app.vision.schemas import VisionImageInput, VisionMediaType

_FORMAT_TO_MEDIA_TYPE: dict[str, VisionMediaType] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


@dataclass(frozen=True)
class PreparedVisionImage:
    """One verified image re-encoded without source metadata for LM Studio."""

    media_type: VisionMediaType
    data_url: str
    original_width: int
    original_height: int
    width: int
    height: int
    input_bytes: int
    processed_bytes: int


def _decode_base64(value: str, *, index: int) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise VisionInputError(
            f"Image {index + 1} was not valid base64.",
            details={"image_index": index},
        ) from exc
    if not raw:
        raise VisionInputError(
            f"Image {index + 1} was empty.",
            details={"image_index": index},
        )
    if len(raw) > settings.vision_max_image_bytes:
        raise VisionInputError(
            f"Image {index + 1} exceeded the per-image byte limit.",
            details={
                "image_index": index,
                "bytes": len(raw),
                "max_bytes": settings.vision_max_image_bytes,
            },
        )
    return raw


def _encode_normalized(image: Image.Image, media_type: VisionMediaType) -> bytes:
    """Re-encode pixels only, stripping EXIF/comments/other source metadata."""

    output = BytesIO()
    if media_type == "image/jpeg":
        normalized = image.convert("RGB")
        normalized.save(output, format="JPEG", quality=92, optimize=True)
    elif media_type == "image/png":
        normalized = image
        if normalized.mode not in {"1", "L", "LA", "P", "RGB", "RGBA"}:
            normalized = normalized.convert("RGBA")
        normalized.save(output, format="PNG", optimize=True)
    else:
        normalized = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        normalized.save(output, format="WEBP", quality=90, method=4)
    return output.getvalue()


def _prepare_one(payload: VisionImageInput, *, index: int) -> PreparedVisionImage:
    raw = _decode_base64(payload.data_base64, index=index)

    try:
        with Image.open(BytesIO(raw)) as opened:
            detected = _FORMAT_TO_MEDIA_TYPE.get((opened.format or "").upper())
            if detected is None:
                raise VisionInputError(
                    f"Image {index + 1} was not PNG, JPEG, or WebP.",
                    details={"image_index": index, "detected_format": opened.format},
                )
            if detected != payload.media_type:
                raise VisionInputError(
                    f"Image {index + 1} media type did not match its bytes.",
                    details={
                        "image_index": index,
                        "declared_media_type": payload.media_type,
                        "detected_media_type": detected,
                    },
                )

            frame_count = int(getattr(opened, "n_frames", 1) or 1)
            if frame_count != 1:
                raise VisionInputError(
                    f"Image {index + 1} was animated or multi-frame; Stage 5 accepts static images only.",
                    details={"image_index": index, "frames": frame_count},
                )

            original_width, original_height = opened.size
            pixels = original_width * original_height
            if pixels > settings.vision_max_pixels:
                raise VisionInputError(
                    f"Image {index + 1} exceeded the pixel limit.",
                    details={
                        "image_index": index,
                        "width": original_width,
                        "height": original_height,
                        "pixels": pixels,
                        "max_pixels": settings.vision_max_pixels,
                    },
                )

            # Correct camera rotation before resizing, then detach from the source
            # file so no lazy decoder or EXIF state survives beyond this block.
            normalized = ImageOps.exif_transpose(opened).copy()
    except VisionInputError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise VisionInputError(
            f"Image {index + 1} could not be decoded safely.",
            details={"image_index": index},
        ) from exc

    normalized.thumbnail(
        (settings.vision_max_side, settings.vision_max_side),
        Image.Resampling.LANCZOS,
    )
    width, height = normalized.size
    encoded = _encode_normalized(normalized, payload.media_type)
    encoded_b64 = base64.b64encode(encoded).decode("ascii")

    return PreparedVisionImage(
        media_type=payload.media_type,
        data_url=f"data:{payload.media_type};base64,{encoded_b64}",
        original_width=original_width,
        original_height=original_height,
        width=width,
        height=height,
        input_bytes=len(raw),
        processed_bytes=len(encoded),
    )


def prepare_vision_images(images: list[VisionImageInput]) -> list[PreparedVisionImage]:
    """Validate a complete image batch and return provider-ready data URLs."""

    if not images:
        raise VisionInputError("At least one image is required.")
    if len(images) > settings.vision_max_images:
        raise VisionInputError(
            "Too many images were supplied.",
            details={"images": len(images), "max_images": settings.vision_max_images},
        )

    prepared: list[PreparedVisionImage] = []
    total_input_bytes = 0
    for index, image in enumerate(images):
        current = _prepare_one(image, index=index)
        total_input_bytes += current.input_bytes
        if total_input_bytes > settings.vision_max_total_bytes:
            raise VisionInputError(
                "The image batch exceeded the total byte limit.",
                details={
                    "bytes": total_input_bytes,
                    "max_bytes": settings.vision_max_total_bytes,
                },
            )
        prepared.append(current)
    return prepared
