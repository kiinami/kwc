"""Embedded image metadata as a JSON EXIF UserComment."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

import pillow_jxl  # noqa: F401  (registers the JXL plugin with Pillow)
from PIL import Image

from .jxl import DEFAULT_PIXEL_BUDGET, ImageTooLarge, probe_dimensions

_USER_COMMENT = 0x9286
_ASCII_PREFIX = b"ASCII\x00\x00\x00"
_UNICODE_PREFIX = b"UNICODE\x00"


@dataclass
class ImageMetadata:
    source_sha256: str | None = None
    timestamp: float | None = None
    phash: str | None = None
    copyright: str | None = None
    generator: str | None = None
    source: str | None = None
    extra: dict[str, object] = field(default_factory=dict)


_KNOWN = {item.name for item in fields(ImageMetadata)} - {"extra"}


def _serialize(meta: ImageMetadata) -> bytes:
    payload: dict[str, object] = {}
    for item in fields(ImageMetadata):
        if item.name == "extra":
            continue
        value = getattr(meta, item.name)
        if value is not None and value != "":
            payload[item.name] = value
    payload.update(meta.extra)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decode_comment(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, (bytes, bytearray)):
        return None
    data = bytes(value)
    if data.startswith(_UNICODE_PREFIX):
        return data[len(_UNICODE_PREFIX) :].decode("utf-16-be", "replace")
    if data.startswith(_ASCII_PREFIX):
        data = data[len(_ASCII_PREFIX) :]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", "replace")


def write_image_metadata(path: Path, meta: ImageMetadata, *, pixel_budget: int = DEFAULT_PIXEL_BUDGET) -> None:
    width, height = probe_dimensions(path)
    if width * height > pixel_budget:
        raise ImageTooLarge(f"{path.name} is {width}x{height}, over the {pixel_budget} pixel budget")
    payload = _ASCII_PREFIX + _serialize(meta)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with Image.open(path) as image:
            image.load()
            exif = Image.Exif()
            raw = image.info.get("exif")
            if raw:
                try:
                    exif.load(raw[6:] if raw.startswith(b"Exif\x00\x00") else raw)
                except Exception:
                    exif = Image.Exif()
            exif[_USER_COMMENT] = payload
            image.save(temporary, format="JXL", lossless=True, exif=exif.tobytes())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_image_metadata(path: Path) -> ImageMetadata:
    try:
        with Image.open(path) as image:
            raw = image.info.get("exif")
    except Exception:
        return ImageMetadata()
    if not raw:
        return ImageMetadata()
    exif = Image.Exif()
    try:
        exif.load(raw[6:] if raw.startswith(b"Exif\x00\x00") else raw)
    except Exception:
        return ImageMetadata()
    text = _decode_comment(exif.get(_USER_COMMENT))
    if text is None:
        return ImageMetadata()
    try:
        payload = json.loads(text)
    except TypeError, ValueError:
        return ImageMetadata()
    if not isinstance(payload, dict):
        return ImageMetadata()
    return ImageMetadata(
        source_sha256=_as_str(payload.get("source_sha256")),
        timestamp=_as_float(payload.get("timestamp")),
        phash=_as_str(payload.get("phash")),
        copyright=_as_str(payload.get("copyright")),
        generator=_as_str(payload.get("generator")),
        source=_as_str(payload.get("source")),
        extra={key: value for key, value in payload.items() if key not in _KNOWN},
    )


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
