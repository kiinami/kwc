"""Filesystem mutations that keep the archive grammar intact."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .metadata import MetadataError, read_metadata, write_metadata
from .naming import ImageName, NameScope, folder_name, image_filename
from .scan import Entity, ImageFile, scan_entity


class IndexExhausted(ValueError):
    """The folder already uses the maximum index."""


class PathEscape(ValueError):
    """A path would leave its allowed root."""


def next_index(images: Sequence[ImageFile]) -> int:
    highest = max((image.index for image in images), default=0)
    if highest >= 9999:
        raise IndexExhausted("folder already uses index 9999")
    return highest + 1


def resolve_under(root: Path, relative: Path | str) -> Path:
    """Resolve a user-supplied path and prove it stays under root."""
    root_path = Path(root).resolve()
    candidate = (root_path / Path(relative)).resolve()
    if not candidate.is_relative_to(root_path):
        raise PathEscape(f"{relative!s} escapes {root_path}")
    return candidate


def rename_image(image: ImageFile, scope: NameScope, new: ImageName) -> Path:
    target = image.path.with_name(image_filename(scope, new))
    if target == image.path:
        return image.path
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    image.path.rename(target)
    return target


def toggle_pick(image: ImageFile, scope: NameScope) -> Path:
    return rename_image(
        image,
        scope,
        ImageName(image.index, not image.picked, image.flags, image.variant),
    )


def _episode_leaves(entity: Entity) -> list[Entity]:
    if entity.kind == "episode":
        return [entity]
    leaves: list[Entity] = []
    for child in entity.children:
        leaves.extend(_episode_leaves(child))
    return leaves


def _rename_plan(entity: Entity, title: str, year: int | None, tmdb_id: int | None) -> list[tuple[Path, Path]]:
    if entity.kind in {"movie", "other"}:
        scope = NameScope(title, year, tmdb_id) if entity.kind == "movie" else NameScope(title)
        images = entity.images
        return [
            (
                image.path,
                image.path.with_name(
                    image_filename(scope, ImageName(image.index, image.picked, image.flags, image.variant))
                ),
            )
            for image in images
        ]
    plan: list[tuple[Path, Path]] = []
    for episode in _episode_leaves(entity):
        scope = NameScope(title, year, tmdb_id, episode.season, episode.episode)
        for image in episode.images:
            plan.append(
                (
                    image.path,
                    image.path.with_name(
                        image_filename(scope, ImageName(image.index, image.picked, image.flags, image.variant))
                    ),
                )
            )
    return plan


def rename_entity(
    folder: Path,
    *,
    new_title: str,
    new_year: int | None = None,
    new_tmdb_id: int | None = None,
) -> Path:
    entity = scan_entity(folder)
    year = new_year if new_year is not None else entity.year
    tmdb_id = new_tmdb_id if new_tmdb_id is not None else entity.tmdb_id
    new_folder_name = (
        folder_name(new_title, year=year, tmdb_id=tmdb_id) if entity.tmdb_id is not None else folder_name(new_title)
    )
    target_folder = folder.with_name(new_folder_name)
    if target_folder != folder and target_folder.exists():
        raise FileExistsError(f"target already exists: {target_folder}")

    plan = _rename_plan(entity, new_title, year, tmdb_id)
    targets: set[Path] = set()
    for source, target in plan:
        if target in targets:
            raise FileExistsError(f"duplicate rename target: {target}")
        targets.add(target)
        if target != source and target.exists():
            raise FileExistsError(f"target already exists: {target}")

    for source, target in plan:
        if source != target:
            source.rename(target)

    try:
        metadata = read_metadata(folder)
    except MetadataError:
        metadata = None
    if metadata is not None:
        write_metadata(folder, metadata)

    if target_folder != folder:
        folder.rename(target_folder)
    return target_folder
