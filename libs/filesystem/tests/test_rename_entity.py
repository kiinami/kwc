from pathlib import Path

import pytest

from filesystem.metadata import FolderMetadata, read_metadata, write_metadata
from filesystem.operations import rename_entity
from filesystem.scan import scan_entity


def _touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def make_movie(root: Path) -> Path:
    folder = root / "Old Name [2001][tmdb-1]"
    _touch(folder / "Old Name [2001][tmdb-1] - 0001.jxl")
    write_metadata(folder, FolderMetadata(kind="movie", title="Old Name", tmdb_id=1))
    return folder


def make_series(root: Path) -> Path:
    folder = root / "Old Show [2016][tmdb-3]"
    folder.mkdir()
    write_metadata(folder, FolderMetadata(kind="series", title="Old Show", tmdb_id=3))
    (folder / "S01").mkdir()
    write_metadata(
        folder / "S01",
        FolderMetadata(kind="season", title="Season 1", season=1),
    )
    episode = folder / "S01" / "E01"
    _touch(episode / "Old Show [2016][tmdb-3] - S01E01 - 0001.jxl")
    write_metadata(episode, FolderMetadata(kind="episode", title="Pilot", season=1, episode="E01"))
    return folder


def test_rename_cascades_to_every_image(tmp_path):
    movie = make_movie(tmp_path)
    new = rename_entity(movie, new_title="New Name", new_year=2002, new_tmdb_id=2)
    assert new.name == "New Name [2002][tmdb-2]"
    assert (new / "New Name [2002][tmdb-2] - 0001.jxl").exists()
    assert not movie.exists()
    assert read_metadata(new).title == "New Name"
    assert read_metadata(new).tmdb_id == 2


def test_series_rename_keeps_season_and_episode_folders(tmp_path):
    series = make_series(tmp_path)
    new = rename_entity(series, new_title="New Series")
    assert (new / "S01" / "E01" / "New Series [2016][tmdb-3] - S01E01 - 0001.jxl").exists()
    assert not series.exists()
    assert read_metadata(new).title == "New Series"


def test_rename_refuses_existing_target(tmp_path):
    movie = make_movie(tmp_path)
    (tmp_path / "Taken [2001][tmdb-1]").mkdir()
    with pytest.raises(FileExistsError):
        rename_entity(movie, new_title="Taken")
    assert movie.exists()


def test_series_scan_after_rename_is_clean(tmp_path):
    series = make_series(tmp_path)
    new = rename_entity(series, new_title="New Series")
    entity = scan_entity(new)
    assert entity.children[0].children[0].images[0].name.startswith("New Series")
