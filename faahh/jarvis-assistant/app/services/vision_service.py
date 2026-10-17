from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path
from uuid import uuid4

import httpx

from app.config import settings

VISION_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "frontend" / "uploads"
DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$", re.IGNORECASE)


class VisionInputError(ValueError):
    """The uploaded image is malformed or not supported."""


class VisionProviderError(RuntimeError):
    """NVIDIA could not analyze the image."""


def _image_extension(image_bytes: bytes) -> str | None:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    return None


def _decode_image(data_url: str) -> tuple[bytes, str, str]:
    match = DATA_URL_RE.fullmatch(data_url)
    if not match:
        raise VisionInputError("Attach a PNG, JPEG, or WebP image.")
    mime_subtype = match.group(1).lower()
    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise VisionInputError("The attached image data is invalid.") from exc
    if not image_bytes:
        raise VisionInputError("The attached image is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise VisionInputError("Image is too large. Choose an image smaller than 5 MB.")

    extension = _image_extension(image_bytes)
    expected_extensions = {"png": "png", "jpeg": "jpg", "webp": "webp"}
    if extension is None or extension != expected_extensions[mime_subtype]:
        raise VisionInputError("The image contents do not match the selected PNG, JPEG, or WebP type.")
    return image_bytes, f"image/{mime_subtype}", extension


def _response_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        text = "\n".join(
            part["text"].strip()
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip()
        )
        return text or None
    return None


async def analyze_image(data_url: str, prompt: str) -> tuple[str, str]:
    image_bytes, mime_type, extension = _decode_image(data_url)
    api_key = settings.NVIDIA_VISION_API_KEY
    if not api_key:
        raise VisionProviderError("Image analysis is not configured. Add NVIDIA_VISION_API_KEY to the local .env file.")

    endpoint = f"{settings.NVIDIA_BASE_URL.rstrip('/')}/chat/completions"
    request_data = {
        "model": VISION_MODEL,
        "messages": [
            {"role": "system", "content": "You are JARVIS, an image analysis assistant. Be accurate, concise, and state when details are unclear."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "max_tokens": 900,
        "temperature": 0.2,
        "stream": False,
    }
    timeout = httpx.Timeout(max(settings.NVIDIA_TIMEOUT_SECONDS, 60.0), connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                json=request_data,
            )
    except httpx.TimeoutException as exc:
        raise VisionProviderError("NVIDIA image analysis timed out. Please try again.") from exc
    except httpx.HTTPError as exc:
        raise VisionProviderError(f"Couldn't connect to NVIDIA image analysis ({type(exc).__name__}).") from exc

    if response.status_code in {401, 403}:
        raise VisionProviderError(f"NVIDIA rejected the vision API key (HTTP {response.status_code}); check the key and model access.")
    if response.status_code == 429:
        raise VisionProviderError("NVIDIA image analysis is rate limited. Wait a moment and try again.")
    if response.status_code == 410:
        raise VisionProviderError("NVIDIA reports that the configured vision model is no longer available (HTTP 410).")
    if response.is_error:
        raise VisionProviderError(f"NVIDIA image analysis returned HTTP {response.status_code}; check model access and the image format.")
    try:
        reply = _response_text(response.json())
    except ValueError as exc:
        raise VisionProviderError("NVIDIA returned an unreadable image analysis response.") from exc
    if not reply:
        raise VisionProviderError("NVIDIA returned no image analysis text.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.{extension}"
    (UPLOAD_DIR / filename).write_bytes(image_bytes)
    return reply, f"/static/uploads/{filename}"
