import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from filesystem.metadata import FolderMetadata, read_metadata, write_metadata
from filesystem.naming import episode_folder, folder_name, season_folder
from filesystem.scan import scan_entity
from media.jxl import encode_jxl_bytes
from tmdb import SeasonDetail, SeriesDetail


def _make_folder(root: Path, name: str, metadata: FolderMetadata | None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    folder = root / name
    if folder.exists():
        raise FileExistsError(f"folder already exists: {folder.name}")
    folder.mkdir()
    if metadata is not None and metadata.has_data():
        write_metadata(folder, metadata)
    return folder


def _write_cover(folder: Path, cover_bytes: bytes | None) -> None:
    if cover_bytes is not None:
        encode_jxl_bytes(cover_bytes, folder / ".cover.jxl")


def create_movie(  # noqa: PLR0913
    *,
    root: Path,
    title: str,
    year: int,
    tmdb_id: int,
    original_title: str | None = None,
    release_date: str | None = None,
    copyright: str = "",
    cover_bytes: bytes | None = None,
) -> Path:
    folder = _make_folder(
        root,
        folder_name(title, year=year, tmdb_id=tmdb_id),
        FolderMetadata(
            original_title=original_title,
            release_date=release_date,
            copyright=copyright or None,
        ),
    )
    _write_cover(folder, cover_bytes)
    return folder


def create_series(*, root: Path, title: str, year: int, tmdb_id: int, copyright: str = "") -> Path:
    return _make_folder(
        root,
        folder_name(title, year=year, tmdb_id=tmdb_id),
        FolderMetadata(copyright=copyright or None),
    )


def create_other(*, root: Path, title: str, copyright: str = "") -> Path:
    return _make_folder(root, folder_name(title), FolderMetadata(copyright=copyright or None))


def _episode_token(number: int) -> str:
    return episode_folder(f"E{number:02d}")


def _create_episodes(parent: Path, season: SeasonDetail) -> None:
    for episode in season.episodes:
        token = _episode_token(episode.episode_number)
        folder = parent / token
        if folder.exists():
            raise FileExistsError(f"episode already exists: {folder}")
        folder.mkdir()


def _create_season(series_path: Path, season: SeasonDetail) -> Path:
    folder = series_path / season_folder(season.season_number)
    if folder.exists():
        raise FileExistsError(f"season already exists: {folder.name}")
    folder.mkdir()
    air_dates = [episode.air_date for episode in season.episodes if episode.air_date]
    first = season.air_date or (min(air_dates) if air_dates else None)
    last = max(air_dates) if air_dates else first
    write_metadata(
        folder,
        FolderMetadata(first_release_date=first, last_release_date=last),
    )
    _create_episodes(folder, season)
    return folder


def build_series_from_tmdb(
    *,
    root: Path,
    detail: SeriesDetail,
    copyright: str = "",
    cover_bytes: bytes | None = None,
) -> Path:
    if not detail.first_air_date:
        raise ValueError("series has no first air date")
    year = int(detail.first_air_date[:4])
    path = create_series(
        root=root,
        title=detail.name,
        year=year,
        tmdb_id=detail.id,
        copyright=copyright,
    )
    metadata = read_metadata(path) or FolderMetadata()
    metadata.original_title = detail.original_name
    metadata.first_release_date = detail.first_air_date
    metadata.last_release_date = detail.last_air_date
    metadata.copyright = metadata.copyright or copyright or None
    write_metadata(path, metadata)
    _write_cover(path, cover_bytes)

    if len(detail.seasons) <= 1:
        for season in detail.seasons:
            _create_episodes(path, season)
    else:
        for season in detail.seasons:
            _create_season(path, season)
    return path


def promote_flat_series(series_path: Path) -> None:
    entity = scan_entity(series_path)
    episodes = [child for child in entity.children if child.kind == "episode"]
    if not episodes:
        return
    groups: dict[int, list] = {}
    for episode in episodes:
        groups.setdefault(episode.season or 1, []).append(episode)
    series_metadata = read_metadata(series_path) or FolderMetadata()
    for number, members in groups.items():
        season_dir = series_path / season_folder(number)
        if not season_dir.exists():
            season_dir.mkdir()
            write_metadata(
                season_dir,
                FolderMetadata(
                    first_release_date=series_metadata.first_release_date,
                    last_release_date=series_metadata.last_release_date,
                ),
            )
        for episode in members:
            target = season_dir / episode.path.name
            if target.exists():
                raise FileExistsError(f"episode already exists: {target}")
            episode.path.rename(target)


def add_season(*, series_path: Path, season: SeasonDetail) -> Path:
    entity = scan_entity(series_path)
    if any(child.kind == "episode" for child in entity.children):
        promote_flat_series(series_path)
    return _create_season(series_path, season)


def delete_entity(*, folder: Path, trash_root: Path) -> Path:
    trash_root.mkdir(parents=True, exist_ok=True)
    target_dir = trash_root / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / folder.name
    if target.exists():
        target = target_dir / f"{folder.name}-{uuid4().hex[:6]}"
    folder.rename(target)
    return target


def set_hidden(*, folder: Path, hidden: bool) -> None:
    metadata = read_metadata(folder) or FolderMetadata()
    metadata.hidden = hidden
    write_metadata(folder, metadata)


def set_cover(*, folder: Path, image: Path) -> Path:
    if not image.is_file():
        raise FileNotFoundError(image)
    destination = folder / ".cover.jxl"
    shutil.copyfile(image, destination)
    return destination
