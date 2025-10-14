from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TypedDict

from django.urls import reverse

from .models import FolderProgress, ImageDecision
from .utils import (
    find_cover_filename,
    get_folder_path,
    list_image_files,
    parse_folder_name,
    thumbnail_url,
    validate_folder_name,
    wallpaper_url,
    wallpapers_root,
)


class GalleryImage(TypedDict):
    name: str
    url: str
    thumb_url: str | None


class FolderImage(TypedDict):
    name: str
    url: str
    thumb_url: str | None
    decision: str


@dataclass(slots=True, frozen=True)
class GalleryContext:
    folder: str
    title: str
    year: str
    year_raw: int | None
    cover_url: str | None
    cover_thumb_url: str | None
    choose_url: str
    images: list[GalleryImage]
    root: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class FolderContext:
    folder: str
    images: list[FolderImage]
    selected_index: int
    selected_image_url: str
    selected_image_name: str
    root: str
    path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def list_gallery_images(folder: str) -> GalleryContext:
    safe_name = validate_folder_name(folder)
    root_path = wallpapers_root()
    target = get_folder_path(safe_name, root_path)

    try:
        files = list_image_files(target)
    except PermissionError:
        files: list[str] = []

    title, year_int = parse_folder_name(safe_name)
    year_display = str(year_int) if year_int is not None else ""

    cover_filename = find_cover_filename(target, files)
    cover_url = (
        wallpaper_url(safe_name, cover_filename, root=root_path)
        if cover_filename
        else None
    )
    cover_thumb_url = (
        thumbnail_url(safe_name, cover_filename, width=420, root=root_path)
        if cover_filename
        else None
    )

    images: list[GalleryImage] = [
        {
            "name": name,
            "url": wallpaper_url(safe_name, name, root=root_path),
            "thumb_url": thumbnail_url(safe_name, name, width=512, root=root_path),
        }
        for name in files
    ]

    choose_url = reverse("choose:folder", kwargs={"folder": safe_name})

    return GalleryContext(
        folder=safe_name,
        title=title,
        year=year_display,
        year_raw=year_int,
        cover_url=cover_url,
        cover_thumb_url=cover_thumb_url,
        choose_url=choose_url,
        images=images,
        root=str(root_path),
    )


def load_folder_context(folder: str) -> FolderContext:
    safe_name = validate_folder_name(folder)
    root_path = wallpapers_root()
    target = get_folder_path(safe_name, root_path)

    try:
        files = list_image_files(target)
    except PermissionError:
        files = []

    decisions_qs = ImageDecision.objects.filter(folder=safe_name)
    decisions = list(decisions_qs.order_by("decided_at", "filename"))
    decision_map = {decision.filename: decision.decision for decision in decisions}

    images: list[FolderImage] = [
        {
            "name": name,
            "url": wallpaper_url(safe_name, name, root=root_path),
            "thumb_url": thumbnail_url(safe_name, name, width=320, root=root_path),
            "decision": decision_map.get(name, ""),
        }
        for name in files
    ]

    selected_index = -1
    progress = FolderProgress.objects.filter(folder=safe_name).first()
    start_index = 0
    if progress and images:
        anchor_idx = -1
        if progress.last_classified_name:
            for idx, image in enumerate(images):
                if image["name"] == progress.last_classified_name:
                    anchor_idx = idx
                    break
        if anchor_idx != -1:
            start_index = anchor_idx + 1
        elif progress.keep_count:
            start_index = progress.keep_count
    if images:
        if start_index >= len(images):
            start_index = len(images) - 1
        if start_index < 0:
            start_index = 0
        for idx in range(start_index, len(images)):
            if not images[idx].get("decision"):
                selected_index = idx
                break
        if selected_index == -1:
            selected_index = start_index

    selected_image_url = (
        images[selected_index]["url"] if images and selected_index >= 0 else ""
    )
    selected_image_name = (
        images[selected_index]["name"] if images and selected_index >= 0 else ""
    )

    return FolderContext(
        folder=safe_name,
        images=images,
        selected_index=selected_index,
        selected_image_url=selected_image_url,
        selected_image_name=selected_image_name,
        root=str(root_path),
        path=str(target),
    )
