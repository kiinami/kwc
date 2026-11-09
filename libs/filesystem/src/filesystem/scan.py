"""Scan the wallpaper tree into typed entities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .metadata import FolderMetadata, MetadataError, read_metadata
from .naming import (
    FLAG_ORDER,
    FolderRef,
    NameScope,
    parse_episode_folder,
    parse_folder_name,
    parse_image_filename,
    parse_season_folder,
)


@dataclass(frozen=True)
class ImageFile:
    path: Path
    name: str
    index: int
    picked: bool
    flags: frozenset[str]
    variant: int | None


@dataclass(frozen=True)
class Entity:
    kind: str
    path: Path
    title: str
    year: int | None
    tmdb_id: int | None
    season: int | None
    episode: str | None
    metadata: FolderMetadata | None
    cover: Path | None
    images: tuple[ImageFile, ...]
    children: tuple[Entity, ...]


@dataclass(frozen=True)
class Archive:
    root: Path
    movies: tuple[Entity, ...]
    series: tuple[Entity, ...]
    others: tuple[Entity, ...]


def _hidden(name: str) -> bool:
    return name.startswith(".")


def _read_meta(path: Path) -> FolderMetadata | None:
    try:
        return read_metadata(path)
    except MetadataError:
        return None


def _cover(path: Path) -> Path | None:
    candidate = path / ".cover.jxl"
    return candidate if candidate.is_file() else None


def _image_key(image: ImageFile) -> tuple[int, bool, tuple[int, ...], int]:
    return (
        image.index,
        bool(image.flags),
        tuple(FLAG_ORDER.index(flag) for flag in FLAG_ORDER if flag in image.flags),
        image.variant or 0,
    )


def _images(path: Path, scope: NameScope) -> tuple[ImageFile, ...]:
    if not path.is_dir():
        return ()
    images: list[ImageFile] = []
    for entry in path.iterdir():
        if not entry.is_file() or entry.is_symlink() or _hidden(entry.name):
            continue
        parsed = parse_image_filename(entry.name, scope)
        if parsed is None:
            continue
        images.append(
            ImageFile(
                path=entry,
                name=entry.name,
                index=parsed.index,
                picked=parsed.picked,
                flags=parsed.flags,
                variant=parsed.variant,
            )
        )
    return tuple(sorted(images, key=_image_key))


def _child_dirs(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(
        (p for p in path.iterdir() if p.is_dir() and not p.is_symlink() and not _hidden(p.name)),
        key=lambda p: p.name.casefold(),
    )


def _has_structure(path: Path) -> bool:
    return any(
        parse_season_folder(child.name) is not None or parse_episode_folder(child.name) is not None
        for child in _child_dirs(path)
    )


def _ref_for(path: Path) -> FolderRef:
    return parse_folder_name(path.name) or FolderRef(path.name)


def _kind_for(path: Path, ref: FolderRef) -> str:
    if parse_season_folder(path.name) is not None:
        return "season"
    if parse_episode_folder(path.name) is not None:
        return "episode"
    if _has_structure(path):
        return "series"
    return "movie" if ref.tmdb_id is not None else "other"


def scan_entity(path: Path, *, kind: str | None = None) -> Entity:
    ref = _ref_for(path)
    meta = _read_meta(path)
    resolved_kind = kind or _kind_for(path, ref)

    if resolved_kind in {"movie", "other"}:
        scope = NameScope(ref.title, ref.year, ref.tmdb_id) if resolved_kind == "movie" else NameScope(ref.title)
        return Entity(
            kind=resolved_kind,
            path=path,
            title=ref.title,
            year=ref.year,
            tmdb_id=ref.tmdb_id,
            season=None,
            episode=None,
            metadata=meta,
            cover=_cover(path),
            images=_images(path, scope),
            children=(),
        )

    if resolved_kind == "series":
        return _scan_series(path, ref, meta)

    if resolved_kind == "season":
        return _scan_season(path, _series_ref_from_parent(path), meta)

    if resolved_kind == "episode":
        parent = path.parent
        season = parse_season_folder(parent.name)
        if season is not None:
            return _scan_episode(path, _series_ref_from_parent(parent), season, meta)
        return _scan_episode(path, _series_ref_from_parent(path), 1, meta)

    raise ValueError(f"unknown entity kind: {resolved_kind}")


def _series_ref_from_parent(path: Path) -> FolderRef:
    parent = path.parent
    if parse_season_folder(path.name) is not None:
        parent = parent.parent
    return _ref_for(parent)


def _scan_series(path: Path, ref: FolderRef, meta: FolderMetadata | None) -> Entity:
    children: list[Entity] = []
    for child in _child_dirs(path):
        season = parse_season_folder(child.name)
        if season is not None:
            children.append(_scan_season(child, ref, _read_meta(child)))
            continue
        episode = parse_episode_folder(child.name)
        if episode is not None:
            children.append(_scan_episode(child, ref, 1, _read_meta(child)))
    return Entity(
        kind="series",
        path=path,
        title=ref.title,
        year=ref.year,
        tmdb_id=ref.tmdb_id,
        season=None,
        episode=None,
        metadata=meta,
        cover=_cover(path),
        images=(),
        children=tuple(children),
    )


def _scan_season(path: Path, series_ref: FolderRef, meta: FolderMetadata | None) -> Entity:
    season = parse_season_folder(path.name)
    if season is None:
        raise ValueError(f"not a season folder: {path.name}")
    children = []
    for child in _child_dirs(path):
        if parse_episode_folder(child.name) is not None:
            children.append(_scan_episode(child, series_ref, season, _read_meta(child)))
    return Entity(
        kind="season",
        path=path,
        title=f"S{season:02d}",
        year=series_ref.year,
        tmdb_id=series_ref.tmdb_id,
        season=season,
        episode=None,
        metadata=meta,
        cover=_cover(path),
        images=(),
        children=tuple(children),
    )


def _scan_episode(path: Path, series_ref: FolderRef, default_season: int, meta: FolderMetadata | None) -> Entity:
    episode = parse_episode_folder(path.name)
    if episode is None:
        raise ValueError(f"not an episode folder: {path.name}")
    season = meta.season if meta is not None and meta.season is not None else default_season
    scope = NameScope(series_ref.title, series_ref.year, series_ref.tmdb_id, season, episode)
    return Entity(
        kind="episode",
        path=path,
        title=episode,
        year=series_ref.year,
        tmdb_id=series_ref.tmdb_id,
        season=season,
        episode=episode,
        metadata=meta,
        cover=_cover(path),
        images=_images(path, scope),
        children=(),
    )


def scan_archive(root: Path) -> Archive:
    if not root.is_dir():
        return Archive(root, (), (), ())
    movies: list[Entity] = []
    series: list[Entity] = []
    others: list[Entity] = []
    entries = (p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and not _hidden(p.name))
    for entry in sorted(entries, key=lambda p: p.name.casefold()):
        entity = scan_entity(entry)
        if entity.kind == "movie":
            movies.append(entity)
        elif entity.kind == "series":
            series.append(entity)
        else:
            others.append(entity)
    return Archive(root, tuple(movies), tuple(series), tuple(others))
