"""Shared data models (TypedDict) for gallery and choose apps."""
from __future__ import annotations

from typing import TypedDict


class MediaFolder(TypedDict):
    """Metadata describing a media folder in the wallpapers directory."""
    
    name: str
    title: str
    year: str
    year_raw: int | None
    year_sort: int
    mtime: int
    cover_filename: str | None
    cover_url: str | None
    cover_thumb_url: str | None


class GalleryImage(TypedDict):
    """Metadata for a single image in the gallery view."""
    
    name: str
    url: str
    thumb_url: str | None
    version_suffix: str
    base_name: str
    versions: list[dict[str, str]]
    versions_json: str


class GallerySection(TypedDict):
    """A group of images for the same season/episode combination."""
    
    title: str
    season: str
    episode: str
    images: list[GalleryImage]
    choose_url: str


class ExtractFolder(TypedDict):
    """Metadata describing a folder in the extraction staging area."""
    
    name: str
    title: str
    season: str
    episode: str
    mtime: int
    image_count: int
    cover_filename: str | None
    cover_url: str | None
    cover_thumb_url: str | None
