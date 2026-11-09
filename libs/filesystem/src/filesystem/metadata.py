"""Folder metadata sidecars (`.metadata.toml`).

Only data that the folder name cannot carry lives here. Identity (kind, title, TMDB id,
season/episode tokens) is derived from the archive path.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

METADATA_FILENAME = ".metadata.toml"
_KNOWN_KEYS = {
    "original_title",
    "release_date",
    "first_release_date",
    "last_release_date",
    "copyright",
    "hidden",
}


class MetadataError(ValueError):
    """The metadata sidecar exists but cannot be understood."""


@dataclass
class FolderMetadata:
    original_title: str | None = None
    release_date: str | None = None
    first_release_date: str | None = None
    last_release_date: str | None = None
    copyright: str | None = None
    hidden: bool = False
    extra: dict[str, object] = field(default_factory=dict)

    def has_data(self) -> bool:
        return any(
            (
                self.original_title,
                self.release_date,
                self.first_release_date,
                self.last_release_date,
                self.copyright,
                self.hidden,
                self.extra,
            )
        )


def read_metadata(folder: Path) -> FolderMetadata | None:
    path = folder / METADATA_FILENAME
    if not path.exists():
        return None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        raise MetadataError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise MetadataError(f"{path} is not a TOML table")
    return FolderMetadata(
        original_title=_optional_str(raw.get("original_title")),
        release_date=_optional_str(raw.get("release_date")),
        first_release_date=_optional_str(raw.get("first_release_date")),
        last_release_date=_optional_str(raw.get("last_release_date")),
        copyright=_optional_str(raw.get("copyright")),
        hidden=bool(raw.get("hidden", False)),
        extra={key: value for key, value in raw.items() if key not in _KNOWN_KEYS},
    )


def write_metadata(folder: Path, data: FolderMetadata) -> None:
    payload: dict[str, Any] = {}
    for key in (
        "original_title",
        "release_date",
        "first_release_date",
        "last_release_date",
        "copyright",
    ):
        value = getattr(data, key)
        if value is not None:
            payload[key] = value
    if data.hidden:
        payload["hidden"] = True
    # Unknown keys survive a rewrite; known keys win over stale duplicates.
    payload = {**data.extra, **payload}
    (folder / METADATA_FILENAME).write_text(tomli_w.dumps(payload), encoding="utf-8")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
