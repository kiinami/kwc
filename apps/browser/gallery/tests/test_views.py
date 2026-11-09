from pathlib import Path
from urllib.parse import quote

import pytest

from filesystem.metadata import FolderMetadata, write_metadata


def touch(path: Path, payload: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


@pytest.fixture
def library(tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path
    film = tmp_path / "Film [2001][tmdb-1]"
    film.mkdir()
    write_metadata(film, FolderMetadata(kind="movie", title="Film", tmdb_id=1))
    touch(film / "Film [2001][tmdb-1] - 0001+.jxl", b"one")
    touch(film / "Film [2001][tmdb-1] - 0002.jxl", b"two")
    touch(film / "Film [2001][tmdb-1] - 0002 [M].jxl", b"mobile")
    touch(film / ".cover.jxl", b"cover")

    hidden = tmp_path / "Hidden"
    hidden.mkdir()
    write_metadata(hidden, FolderMetadata(kind="other", title="Hidden", hidden=True))
    touch(hidden / "Hidden - 0001.jxl")

    empty = tmp_path / "Empty"
    empty.mkdir()
    write_metadata(empty, FolderMetadata(kind="other", title="Empty"))
    return tmp_path


def test_index_lists_visible_entities(client, library):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Film" in response.content
    assert b"Hidden" not in response.content
    assert b"Empty" not in response.content
    assert b".metadata.toml" not in response.content


def test_folder_hides_variants_and_shows_counts(client, library):
    response = client.get("/browse/" + quote("Film [2001][tmdb-1]") + "?curated=0")
    assert response.status_code == 200
    assert response.content.count(b"data-index=") == 2
    assert b"1 / 2" in response.content


def test_folder_curated_filter(client, library):
    curated = client.get("/browse/" + quote("Film [2001][tmdb-1]") + "?curated=1")
    everything = client.get("/browse/" + quote("Film [2001][tmdb-1]") + "?curated=0")
    assert curated.content.count(b"data-index=") == 1
    assert everything.content.count(b"data-index=") == 2


def test_original_serves_the_file(client, library):
    url = "/i/" + quote("Film [2001][tmdb-1]/Film [2001][tmdb-1] - 0001+.jxl")
    response = client.get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"one"
    assert response["Content-Type"] == "image/jxl"


def test_original_download_sets_attachment(client, library):
    url = "/i/" + quote("Film [2001][tmdb-1]/Film [2001][tmdb-1] - 0001+.jxl") + "?download=1"
    response = client.get(url)
    assert response["Content-Disposition"].startswith("attachment")


def test_traversal_is_rejected(client, library):
    assert client.get("/i/../etc/passwd").status_code == 404
    assert client.get("/browse/../etc").status_code == 404


def test_hidden_folder_is_not_browsable(client, library):
    assert client.get("/browse/Hidden").status_code == 404
