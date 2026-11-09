"""Report archive structure problems without stopping at the first one."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .metadata import FolderMetadata, MetadataError, read_metadata
from .naming import (
    FolderRef,
    NameScope,
    parse_episode_folder,
    parse_folder_name,
    parse_image_filename,
    parse_season_folder,
)

_LOOSE_INDEX = re.compile(r" - (\d{4,})(?:[+ ]|\.)")


@dataclass(frozen=True)
class Issue:
    path: Path
    code: str
    message: str


def _hidden(name: str) -> bool:
    return name.startswith(".")


def _dirs(path: Path) -> list[Path]:
    return sorted(
        (p for p in path.iterdir() if p.is_dir() and not p.is_symlink() and not _hidden(p.name)),
        key=lambda p: p.name.casefold(),
    )


def _metadata(path: Path, issues: list[Issue]) -> FolderMetadata | None:
    marker = path / ".metadata.toml"
    if not marker.exists():
        issues.append(Issue(path, "missing-metadata", "folder has no .metadata.toml"))
        return None
    try:
        return read_metadata(path)
    except MetadataError as exc:
        issues.append(Issue(path, "metadata-invalid", str(exc)))
        return None


def _images(path: Path, scope: NameScope, issues: list[Issue]) -> int:
    seen: dict[tuple[int, frozenset[str], int | None], str] = {}
    count = 0
    for entry in sorted(path.iterdir(), key=lambda p: p.name.casefold()):
        if (
            not entry.is_file()
            or entry.is_symlink()
            or _hidden(entry.name)
            or entry.name in {".metadata.toml", ".cover.jxl"}
        ):
            continue
        parsed = parse_image_filename(entry.name, scope)
        if parsed is None:
            loose = _LOOSE_INDEX.search(entry.name)
            if loose and not 1 <= int(loose.group(1)) <= 9999:
                issues.append(Issue(entry, "index-out-of-range", "index must be between 0001 and 9999"))
            else:
                issues.append(Issue(entry, "unparsed-file", "file does not match the archive grammar"))
            continue
        key = (parsed.index, parsed.flags, parsed.variant)
        if key in seen:
            issues.append(Issue(entry, "duplicate-index", f"same index/type as {seen[key]}"))
        else:
            seen[key] = entry.name
        count += 1
    return count


def _cover(path: Path, has_images: bool, issues: list[Issue]) -> None:
    if (path / ".cover.jxl").exists() and not has_images:
        issues.append(Issue(path, "orphan-cover", "cover exists but the folder has no images"))


def _validate_flat(path: Path, ref: FolderRef, kind: str, meta: FolderMetadata | None, issues: list[Issue]) -> None:
    scope = NameScope(ref.title, ref.year, ref.tmdb_id) if kind == "movie" else NameScope(ref.title)
    count = _images(path, scope, issues)
    _cover(path, count > 0, issues)


def _validate_episode(path: Path, series_ref: FolderRef, default_season: int, issues: list[Issue]) -> None:
    episode = parse_episode_folder(path.name)
    if episode is None:
        issues.append(Issue(path, "unparsed-folder", "episode folder token is invalid"))
        return
    meta = _metadata(path, issues)
    season = meta.season if meta is not None and meta.season is not None else default_season
    scope = NameScope(series_ref.title, series_ref.year, series_ref.tmdb_id, season, episode)
    count = _images(path, scope, issues)
    _cover(path, count > 0, issues)


def _validate_season(path: Path, series_ref: FolderRef, issues: list[Issue]) -> None:
    season = parse_season_folder(path.name)
    if season is None:
        issues.append(Issue(path, "unparsed-folder", "season folder token is invalid"))
        return
    _metadata(path, issues)
    for child in _dirs(path):
        if parse_episode_folder(child.name) is not None:
            _validate_episode(child, series_ref, season, issues)
        else:
            issues.append(Issue(child, "unparsed-folder", "expected an episode folder"))


def _validate_series(path: Path, ref: FolderRef, issues: list[Issue]) -> None:
    seasons: list[Path] = []
    episodes: list[Path] = []
    for child in _dirs(path):
        if parse_season_folder(child.name) is not None:
            seasons.append(child)
        elif parse_episode_folder(child.name) is not None:
            episodes.append(child)
        else:
            issues.append(Issue(child, "unparsed-folder", "expected a season or episode folder"))
    if seasons and episodes:
        issues.append(Issue(path, "mixed-layout", "series mixes season folders and episode folders"))
    for season in seasons:
        _validate_season(season, ref, issues)
    for episode in episodes:
        _validate_episode(episode, ref, 1, issues)


def validate_archive(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    if not root.is_dir():
        return issues
    for top in _dirs(root):
        ref = parse_folder_name(top.name)
        if ref is None:
            issues.append(Issue(top, "unparsed-folder", "folder name does not match the archive grammar"))
            continue
        meta = _metadata(top, issues)
        kind = meta.kind if meta is not None and meta.kind in {"movie", "series", "other"} else None
        if kind is None:
            structure = any(
                parse_season_folder(child.name) is not None or parse_episode_folder(child.name) is not None
                for child in _dirs(top)
            )
            kind = "series" if structure else ("movie" if ref.tmdb_id is not None else "other")
        if kind == "series":
            _validate_series(top, ref, issues)
        else:
            _validate_flat(top, ref, kind, meta, issues)
    return issues
