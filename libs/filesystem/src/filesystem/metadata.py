"""Folder metadata sidecars (`.metadata.toml`)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

METADATA_FILENAME = ".metadata.toml"
_KNOWN_KEYS = {
    "kind",
    "title",
    "original_title",
    "release_date",
    "first_release_date",
    "last_release_date",
    "season",
    "episode",
    "tmdb_id",
    "copyright",
    "hidden",
}


class MetadataError(ValueError):
    """The metadata sidecar exists but cannot be understood."""


@dataclass
class FolderMetadata:
    kind: str
    title: str
    original_title: str | None = None
    release_date: str | None = None
    first_release_date: str | None = None
    last_release_date: str | None = None
    season: int | None = None
    episode: str | None = None
    tmdb_id: int | None = None
    copyright: str | None = None
    hidden: bool = False
    extra: dict[str, object] = field(default_factory=dict)


def read_metadata(folder: Path) -> FolderMetadata | None:
    path = folder / METADATA_FILENAME
    if not path.exists():
        return None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise MetadataError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise MetadataError(f"{path} is not a TOML table")
    title = raw.get("title")
    if not isinstance(title, str):
        raise MetadataError(f"{path} has no string title")
    data = FolderMetadata(
        kind=str(raw.get("kind", "")),
        title=title,
        original_title=_optional_str(raw.get("original_title")),
        release_date=_optional_str(raw.get("release_date")),
        first_release_date=_optional_str(raw.get("first_release_date")),
        last_release_date=_optional_str(raw.get("last_release_date")),
        season=_optional_int(raw.get("season")),
        episode=_optional_str(raw.get("episode")),
        tmdb_id=_optional_int(raw.get("tmdb_id")),
        copyright=_optional_str(raw.get("copyright")),
        hidden=bool(raw.get("hidden", False)),
        extra={key: value for key, value in raw.items() if key not in _KNOWN_KEYS},
    )
    return data


def write_metadata(folder: Path, data: FolderMetadata) -> None:
    payload: dict[str, Any] = {}
    for key in ("kind", "title"):
        value = getattr(data, key)
        if not value:
            raise MetadataError(f"{key} is required")
        payload[key] = value
    for key in (
        "original_title",
        "release_date",
        "first_release_date",
        "last_release_date",
        "season",
        "episode",
        "tmdb_id",
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


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None
