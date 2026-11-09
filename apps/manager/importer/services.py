from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from filesystem.naming import ImageName, NameScope, image_filename, parse_folder_name, parse_season_folder
from filesystem.scan import Entity, scan_entity

DEFAULT_TYPE_MAP: dict[str, frozenset[str]] = {
    "U": frozenset({"U"}),
    "M": frozenset({"M"}),
    "UM": frozenset({"U", "M"}),
}


@dataclass(frozen=True)
class ImportMatch:
    source: Path
    index: int
    flags: frozenset[str]
    variant: int | None
    target_name: str


@dataclass(frozen=True)
class ImportPlan:
    matches: tuple[ImportMatch, ...]
    unmatched: tuple[Path, ...]
    collisions: tuple[str, ...]


def _scope_for(target: Path, entity: Entity) -> NameScope:
    if entity.kind == "movie":
        return NameScope(entity.title, entity.year, entity.tmdb_id)
    if entity.kind == "other":
        return NameScope(entity.title)
    if entity.kind == "episode":
        parent = target.parent
        series_dir = parent.parent if parse_season_folder(parent.name) is not None else parent
        ref = parse_folder_name(series_dir.name)
        if ref is None:
            raise ValueError("episode folder is not under a recognizable series")
        return NameScope(ref.title, ref.year, ref.tmdb_id, entity.season, entity.episode)
    raise ValueError("import into a movie, episode, or other folder")


def build_plan(
    *,
    source_root: Path,
    target: Path,
    pattern: re.Pattern[str],
    type_map: Mapping[str, frozenset[str]],
) -> ImportPlan:
    if "index" not in pattern.groupindex:
        raise ValueError("regex must have a named group 'index'")
    source_root = source_root.resolve()
    target = target.resolve()
    if not source_root.is_dir():
        raise ValueError(f"source folder does not exist: {source_root}")
    if not target.is_dir():
        raise ValueError(f"target folder does not exist: {target}")
    entity = scan_entity(target)
    scope = _scope_for(target, entity)

    matches: list[ImportMatch] = []
    unmatched: list[Path] = []
    collisions: list[str] = []
    seen: dict[tuple[int, frozenset[str], int | None], Path] = {}
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(source_root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        resolution = source.resolve()
        if not resolution.is_relative_to(source_root):
            collisions.append(f"{relative}: escapes the source root")
            continue
        match = pattern.search(source.stem)
        if match is None:
            unmatched.append(source)
            continue
        index = int(match.group("index"))
        if not 1 <= index <= 9999:
            collisions.append(f"{relative}: index out of range")
            continue
        token = (match.groupdict().get("type") or "").upper()
        flags = frozenset()
        if token:
            mapped = type_map.get(token)
            if mapped is None:
                unmatched.append(source)
                continue
            flags = frozenset(mapped)
        name = image_filename(scope, ImageName(index, False, flags, None))
        key = (index, flags, None)
        if key in seen:
            collisions.append(f"{relative}: duplicates {seen[key].name}")
            continue
        seen[key] = source
        if (target / name).exists() or (target / name.replace(".jxl", "+.jxl")).exists():
            collisions.append(f"{relative}: target already exists as {name}")
            continue
        matches.append(ImportMatch(source=source, index=index, flags=flags, variant=None, target_name=name))

    return ImportPlan(tuple(matches), tuple(unmatched), tuple(collisions))
