from io import BytesIO

import pytest
from folders.services import create_movie, create_other, create_series
from PIL import Image

from filesystem.metadata import read_metadata


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 48), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_create_movie_writes_metadata(tmp_path):
    path = create_movie(
        root=tmp_path,
        title="Film",
        year=2001,
        tmdb_id=1,
        original_title="Original Film",
        release_date="2001-01-01",
    )
    assert path.name == "Film [2001][tmdb-1]"
    data = read_metadata(path)
    assert (data.original_title, data.release_date) == ("Original Film", "2001-01-01")


def test_create_movie_can_write_a_cover(tmp_path):
    path = create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1, cover_bytes=png_bytes())
    with Image.open(path / ".cover.jxl") as cover:
        assert cover.size == (32, 48)


def test_create_series_starts_without_metadata(tmp_path):
    path = create_series(root=tmp_path, title="Show", year=2020, tmdb_id=2)
    assert path.name == "Show [2020][tmdb-2]"
    assert read_metadata(path) is None


def test_create_other_has_no_metadata(tmp_path):
    path = create_other(root=tmp_path, title="Other")
    assert path.name == "Other"
    assert read_metadata(path) is None


def test_create_refuses_duplicate(tmp_path):
    create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1)
    with pytest.raises(FileExistsError):
        create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1)


def test_create_rejects_invalid_title(tmp_path):
    with pytest.raises(ValueError):
        create_movie(root=tmp_path, title="Bad/Title", year=2001, tmdb_id=1)
