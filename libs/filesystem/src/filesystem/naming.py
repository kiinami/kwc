"""Archive naming grammar.

The filenames are the database: these functions are the only place that knows how
folders and images are spelled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FLAG_ORDER = ("U", "M", "P", "A")
_FLAGS = frozenset(FLAG_ORDER)
_FOLDER_RE = re.compile(r"^(?P<title>.+?) \[(?P<year>\d{4})\]\[tmdb-(?P<tmdb_id>\d+)\]$")
_SEASON_RE = re.compile(r"^S(?P<season>\d{2})$")
_EPISODE_RE = re.compile(r"^(?P<episode>E\d{2}|EIN\d?|EOUT\d?)$", re.IGNORECASE)
_TYPE_RE = re.compile(r"^\[(?P<flags>[UMPA]+)(?P<variant>\d+)?\]$")


@dataclass(frozen=True)
class FolderRef:
    title: str
    year: int | None = None
    tmdb_id: int | None = None


@dataclass(frozen=True)
class ImageName:
    index: int
    picked: bool = False
    flags: frozenset[str] = frozenset()
    variant: int | None = None


@dataclass(frozen=True)
class NameScope:
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    season: int | None = None
    episode: str | None = None


def _validate_title(title: str) -> None:
    if not title or title != title.strip():
        raise ValueError("title must be non-empty and have no surrounding whitespace")
    if any(char in title for char in "[]/\\"):
        raise ValueError("title must not contain brackets or path separators")


def _validate_index(index: int) -> None:
    if not 1 <= index <= 9999:
        raise ValueError(f"index out of range: {index}")


def folder_name(title: str, *, year: int | None = None, tmdb_id: int | None = None) -> str:
    _validate_title(title)
    if (year is None) != (tmdb_id is None):
        raise ValueError("year and tmdb_id must be provided together")
    if year is None:
        return title
    if not 1000 <= year <= 9999:
        raise ValueError(f"year out of range: {year}")
    if tmdb_id <= 0:
        raise ValueError("tmdb_id must be positive")
    return f"{title} [{year:04d}][tmdb-{tmdb_id}]"


def parse_folder_name(name: str) -> FolderRef | None:
    match = _FOLDER_RE.fullmatch(name)
    if match:
        return FolderRef(match.group("title"), int(match.group("year")), int(match.group("tmdb_id")))
    if "[" in name or "]" in name:
        return None
    try:
        _validate_title(name)
    except ValueError:
        return None
    return FolderRef(name)


def season_folder(season: int) -> str:
    if not 0 <= season <= 99:
        raise ValueError(f"season out of range: {season}")
    return f"S{season:02d}"


def parse_season_folder(name: str) -> int | None:
    match = _SEASON_RE.fullmatch(name)
    return int(match.group("season")) if match else None


def episode_folder(episode: str) -> str:
    match = _EPISODE_RE.fullmatch(episode)
    if not match:
        raise ValueError(f"invalid episode token: {episode}")
    return match.group("episode").upper()


def parse_episode_folder(name: str) -> str | None:
    match = _EPISODE_RE.fullmatch(name)
    return match.group("episode").upper() if match else None


def _normalize_flags(flags: frozenset[str]) -> tuple[str, ...]:
    unknown = set(flags) - _FLAGS
    if unknown:
        raise ValueError(f"unknown type flags: {sorted(unknown)}")
    return tuple(flag for flag in FLAG_ORDER if flag in flags)


def format_type(flags: frozenset[str], variant: int | None) -> str:
    ordered = _normalize_flags(flags)
    if not ordered:
        return ""
    if variant is not None and variant < 1:
        raise ValueError("variant must be positive")
    suffix = "" if variant is None else str(variant)
    return f"[{''.join(ordered)}{suffix}]"


def parse_type(token: str) -> tuple[frozenset[str], int | None] | None:
    match = _TYPE_RE.fullmatch(token)
    if not match:
        return None
    raw = match.group("flags")
    if len(set(raw)) != len(raw):
        return None
    flags = frozenset(raw)
    variant = int(match.group("variant")) if match.group("variant") else None
    return flags, variant


def _scope_prefix(scope: NameScope) -> str:
    if (scope.season is None) != (scope.episode is None):
        raise ValueError("season and episode must be provided together")
    prefix = folder_name(scope.title, year=scope.year, tmdb_id=scope.tmdb_id)
    if scope.season is not None:
        prefix = f"{prefix} - {season_folder(scope.season)}{episode_folder(scope.episode or '')}"
    return prefix


def image_filename(scope: NameScope, image: ImageName) -> str:
    _validate_index(image.index)
    pick = "+" if image.picked else ""
    type_token = format_type(image.flags, image.variant)
    suffix = f" {type_token}" if type_token else ""
    return f"{_scope_prefix(scope)} - {image.index:04d}{pick}{suffix}.jxl"


def parse_image_filename(filename: str, scope: NameScope) -> ImageName | None:
    prefix = re.escape(_scope_prefix(scope))
    match = re.fullmatch(
        rf"{prefix} - (?P<index>\d{{4}})(?P<pick>\+)?(?: \[(?P<type>[UMPA]+)(?P<variant>\d+)?\])?\.jxl",
        filename,
    )
    if not match:
        return None
    index = int(match.group("index"))
    if not 1 <= index <= 9999:
        return None
    flags: frozenset[str] = frozenset()
    variant: int | None = None
    type_flags = match.group("type")
    if type_flags is not None:
        if len(set(type_flags)) != len(type_flags):
            return None
        flags = frozenset(type_flags)
        variant = int(match.group("variant")) if match.group("variant") else None
    return ImageName(index, bool(match.group("pick")), flags, variant)
