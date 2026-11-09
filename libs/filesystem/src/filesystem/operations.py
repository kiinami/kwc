"""Filesystem mutations that keep the archive grammar intact."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .naming import ImageName, NameScope, image_filename
from .scan import ImageFile


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
