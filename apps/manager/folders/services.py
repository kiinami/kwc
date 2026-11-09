import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from filesystem.metadata import FolderMetadata, read_metadata, write_metadata
from filesystem.naming import episode_folder, folder_name, season_folder
from filesystem.scan import scan_entity
from tmdb import SeasonDetail, SeriesDetail


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


def _episode_token(number: int) -> str:
    return episode_folder(f"E{number:02d}")


def _write_episode(folder: Path, season: SeasonDetail, number: int, name: str, air_date: str | None) -> None:
    write_metadata(
        folder,
        FolderMetadata(
            kind="episode",
            title=name,
            season=season.season_number,
            episode=_episode_token(number),
            first_release_date=air_date,
            last_release_date=air_date,
        ),
    )


def _create_episodes(parent: Path, season: SeasonDetail) -> None:
    for episode in season.episodes:
        token = _episode_token(episode.episode_number)
        folder = parent / token
        if folder.exists():
            raise FileExistsError(f"episode already exists: {folder}")
        folder.mkdir()
        _write_episode(folder, season, episode.episode_number, episode.name, episode.air_date)


def _create_season(series_path: Path, season: SeasonDetail) -> Path:
    folder = series_path / season_folder(season.season_number)
    if folder.exists():
        raise FileExistsError(f"season already exists: {folder.name}")
    folder.mkdir()
    write_metadata(
        folder,
        FolderMetadata(
            kind="season",
            title=season.name or f"Season {season.season_number}",
            season=season.season_number,
            first_release_date=season.air_date,
            last_release_date=season.air_date,
        ),
    )
    _create_episodes(folder, season)
    return folder


def build_series_from_tmdb(*, root: Path, detail: SeriesDetail, copyright: str = "") -> Path:
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
    metadata = read_metadata(path)
    if metadata is not None:
        metadata.original_title = detail.original_name
        metadata.first_release_date = detail.first_air_date
        metadata.last_release_date = detail.last_air_date
        write_metadata(path, metadata)

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
    for number, members in groups.items():
        season_dir = series_path / season_folder(number)
        if not season_dir.exists():
            season_dir.mkdir()
            write_metadata(
                season_dir,
                FolderMetadata(kind="season", title=f"Season {number}", season=number),
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
    metadata = read_metadata(folder)
    if metadata is None:
        raise FileNotFoundError(f"{folder} has no .metadata.toml")
    metadata.hidden = hidden
    write_metadata(folder, metadata)


def set_cover(*, folder: Path, image: Path) -> Path:
    if not image.is_file():
        raise FileNotFoundError(image)
    destination = folder / ".cover.jxl"
    shutil.copyfile(image, destination)
    return destination
