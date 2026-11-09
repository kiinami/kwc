import pytest
from folders.services import create_movie, create_other, create_series

from filesystem.metadata import read_metadata


def test_create_movie_writes_metadata(tmp_path):
    path = create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1)
    assert path.name == "Film [2001][tmdb-1]"
    data = read_metadata(path)
    assert (data.kind, data.title, data.tmdb_id) == ("movie", "Film", 1)


def test_create_series_writes_metadata(tmp_path):
    path = create_series(root=tmp_path, title="Show", year=2020, tmdb_id=2)
    assert read_metadata(path).kind == "series"


def test_create_other_has_no_tmdb(tmp_path):
    path = create_other(root=tmp_path, title="Other")
    assert path.name == "Other"
    assert read_metadata(path).kind == "other"


def test_create_refuses_duplicate(tmp_path):
    create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1)
    with pytest.raises(FileExistsError):
        create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1)


def test_create_rejects_invalid_title(tmp_path):
    with pytest.raises(ValueError):
        create_movie(root=tmp_path, title="Bad/Title", year=2001, tmdb_id=1)
