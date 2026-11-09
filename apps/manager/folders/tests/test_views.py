from urllib.parse import quote

import pytest
from folders.services import create_movie

from filesystem.metadata import FolderMetadata, write_metadata
from tmdb import MovieDetail


@pytest.fixture
def library(tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path
    folder = create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1)
    (folder / "Film [2001][tmdb-1] - 0001.jxl").write_text("")
    return tmp_path


def test_list_view_lists_entities(client, library):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Film" in response.content


def test_detail_view_lists_images(client, library):
    response = client.get("/folders/" + quote("Film [2001][tmdb-1]"))
    assert response.status_code == 200
    assert b"0001.jxl" in response.content


def test_detail_rejects_traversal(client, library):
    response = client.get("/folders/../etc/passwd")
    assert response.status_code == 404


def test_create_view_creates_folder(client, library):
    response = client.post(
        "/folders/new",
        {"kind": "movie", "title": "New", "year": 2002, "tmdb_id": 2, "copyright": "(c) Studio"},
    )
    assert response.status_code == 302
    assert (library / "New [2002][tmdb-2]").is_dir()


def test_search_without_token_shows_message(client, library, settings):
    settings.TMDB_READ_TOKEN = ""
    response = client.get("/folders/search", {"kind": "movie", "query": "Film"})
    assert b"TMDB_READ_TOKEN" in response.content


def test_search_uses_tmdb(client, library, settings, monkeypatch):
    settings.TMDB_READ_TOKEN = "token"

    class FakeClient:
        def __init__(self, token):
            assert token == "token"

        def search_movies(self, query, year=None):
            return [MovieDetail(3, "Found", "Found", "1999-01-01")]

    monkeypatch.setattr("folders.views.TMDBClient", FakeClient)
    response = client.get("/folders/search", {"kind": "movie", "query": "Found"})
    assert b"Found" in response.content


def test_hidden_folder_is_marked_in_list(client, library):
    folder = library / "Hidden"
    folder.mkdir()
    write_metadata(folder, FolderMetadata(kind="other", title="Hidden", hidden=True))
    response = client.get("/")
    assert b"hidden" in response.content
