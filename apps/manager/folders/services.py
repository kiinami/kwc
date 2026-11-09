from pathlib import Path

from filesystem.metadata import FolderMetadata, write_metadata
from filesystem.naming import folder_name


def _make_folder(root: Path, name: str, metadata: FolderMetadata) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    folder = root / name
    if folder.exists():
        raise FileExistsError(f"folder already exists: {folder.name}")
    folder.mkdir()
    write_metadata(folder, metadata)
    return folder


def create_movie(*, root: Path, title: str, year: int, tmdb_id: int, copyright: str = "") -> Path:
    return _make_folder(
        root,
        folder_name(title, year=year, tmdb_id=tmdb_id),
        FolderMetadata(
            kind="movie",
            title=title,
            tmdb_id=tmdb_id,
            copyright=copyright or None,
        ),
    )


def create_series(*, root: Path, title: str, year: int, tmdb_id: int, copyright: str = "") -> Path:
    return _make_folder(
        root,
        folder_name(title, year=year, tmdb_id=tmdb_id),
        FolderMetadata(
            kind="series",
            title=title,
            tmdb_id=tmdb_id,
            copyright=copyright or None,
        ),
    )


def create_other(*, root: Path, title: str, copyright: str = "") -> Path:
    return _make_folder(
        root,
        folder_name(title),
        FolderMetadata(kind="other", title=title, copyright=copyright or None),
    )
