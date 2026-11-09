from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from filesystem.naming import ImageName, NameScope, image_filename, parse_folder_name, parse_season_folder
from filesystem.scan import Entity, scan_entity
from jobs.worker import JobContext
from media.hashing import sha256_file
from media.jxl import DEFAULT_PIXEL_BUDGET, encode_jxl
from media.metadata import ImageMetadata, write_image_metadata

DEFAULT_TYPE_MAP: dict[str, frozenset[str]] = {
    "U": frozenset({"U"}),
    "M": frozenset({"M"}),
    "UM": frozenset({"U", "M"}),
    "E": frozenset({"A"}),
}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif", ".avif"}


@dataclass(frozen=True)
class DetectedPattern:
    regex: str
    width: int
    matched: int
    total: int
    samples: tuple[tuple[str, int, str], ...]


def detect_pattern(source_root: Path) -> DetectedPattern | None:
    files = [
        path
        for path in source_root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and not any(part.startswith(".") for part in path.relative_to(source_root).parts)
    ]
    if not files:
        return None
    candidates: list[tuple[int, int, str, list[tuple[str, int, str]]]] = []
    for width in (4, 3, 2, 1):
        regex = rf"(?P<index>\d{{{width}}})(?P<type>[A-Z]{{0,3}})$"
        pattern = re.compile(regex)
        matched = 0
        samples: list[tuple[str, int, str]] = []
        for path in files:
            match = pattern.search(path.stem)
            if not match:
                continue
            index = int(match.group("index"))
            if not 1 <= index <= 9999:
                continue
            matched += 1
            if len(samples) < 5:
                samples.append((path.name, index, (match.groupdict().get("type") or "").upper()))
        if matched:
            candidates.append((matched, width, regex, samples))
    if not candidates:
        return None
    matched, width, regex, samples = max(candidates, key=lambda item: (item[0], item[1]))
    return DetectedPattern(regex=regex, width=width, matched=matched, total=len(files), samples=tuple(samples))


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


@dataclass(frozen=True)
class _Candidate:
    source: Path
    index: int
    flags: frozenset[str]
    reduced: bool


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

    candidates: dict[int, list[_Candidate]] = {}
    unmatched: list[Path] = []
    collisions: list[str] = []
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
        reduced = "R" in token
        base_token = token.replace("R", "")
        flags = frozenset()
        if base_token:
            mapped = type_map.get(base_token)
            if mapped is None:
                unmatched.append(source)
                continue
            flags = frozenset(mapped)
        candidates.setdefault(index, []).append(_Candidate(source=source, index=index, flags=flags, reduced=reduced))

    matches: list[ImportMatch] = []
    planned: dict[str, Path] = {}

    def add(candidate: _Candidate, target_flags: frozenset[str]) -> None:
        name = image_filename(scope, ImageName(candidate.index, False, target_flags, None))
        if name in planned:
            collisions.append(f"{candidate.source.name}: target {name} is also used by {planned[name].name}")
            return
        if (target / name).exists() or (target / name.replace(".jxl", "+.jxl")).exists():
            collisions.append(f"{candidate.source.name}: target already exists as {name}")
            return
        planned[name] = candidate.source
        matches.append(
            ImportMatch(
                source=candidate.source,
                index=candidate.index,
                flags=target_flags,
                variant=None,
                target_name=name,
            )
        )

    for index in sorted(candidates):
        groups: dict[frozenset[str], dict[str, list[_Candidate]]] = {}
        for candidate in candidates[index]:
            bucket = groups.setdefault(candidate.flags, {"normal": [], "reduced": []})
            bucket["reduced" if candidate.reduced else "normal"].append(candidate)
        for flags, bucket in groups.items():
            normals = bucket["normal"]
            reduceds = bucket["reduced"]
            for extra in normals[1:]:
                collisions.append(f"{extra.source.name}: duplicate base for index {index:04d}")
            for extra in reduceds[1:]:
                collisions.append(f"{extra.source.name}: duplicate reduced image for index {index:04d}")
            normal_flags = flags | {"U"} if reduceds else flags
            if normals:
                add(normals[0], normal_flags)
            if reduceds:
                add(reduceds[0], flags)

    matches.sort(key=lambda match: (match.index, tuple(sorted(match.flags)), match.source.name))
    return ImportPlan(tuple(matches), tuple(unmatched), tuple(collisions))


def run_plan(  # noqa: PLR0913
    *,
    plan: ImportPlan,
    target: Path,
    pick_all: bool,
    copyright: str,
    ctx: JobContext,
    pixel_budget: int = DEFAULT_PIXEL_BUDGET,
) -> dict:
    if plan.collisions:
        raise ValueError("import plan has collisions: " + "; ".join(plan.collisions[:5]))
    target = target.resolve()
    scope = _scope_for(target, scan_entity(target))
    imported = 0
    total = len(plan.matches)
    for current, match in enumerate(plan.matches, start=1):
        ctx.check_cancelled()
        final = target / image_filename(
            scope,
            ImageName(match.index, pick_all, match.flags, match.variant),
        )
        if final.exists():
            raise FileExistsError(f"target already exists: {final.name}")
        temporary = target / f".import-{match.index:04d}-{current}.tmp"
        try:
            encode_jxl(match.source, temporary, pixel_budget=pixel_budget)
            write_image_metadata(
                temporary,
                ImageMetadata(
                    source_sha256=sha256_file(match.source),
                    copyright=copyright or None,
                    generator="import",
                    source=match.source.name,
                ),
                pixel_budget=pixel_budget,
            )
            temporary.replace(final)
        finally:
            temporary.unlink(missing_ok=True)
        imported += 1
        ctx.progress(current, total=total, message=f"imported {current}/{total}")
    return {"imported": imported}
