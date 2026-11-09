from io import BytesIO
from urllib.parse import quote

import pytest
from folders.services import create_movie, create_series
from jobs.models import Job
from PIL import Image

from filesystem.metadata import FolderMetadata, write_metadata
from tmdb import MovieDetail


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 48), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakePosterClient:
    def __init__(self, token):
        assert token == "token"

    def posters(self, tmdb_id, kind="movie"):
        return ["/p.jpg"]

    def image_url(self, path, size="w500"):
        return f"https://image.tmdb.org/t/p/{size}{path}"

    def download_image(self, path, size="original"):
        return png_bytes()


@pytest.fixture
def library(tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path
    folder = create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1)
    (folder / "Film [2001][tmdb-1] - 0001.jxl").write_text("")
    return tmp_path


def test_list_view_lists_entities(auth_client, library):
    response = auth_client.get("/")
    assert response.status_code == 200
    assert b"Film" in response.content


def test_detail_view_lists_images(auth_client, library):
    response = auth_client.get("/folders/" + quote("Film [2001][tmdb-1]"))
    assert response.status_code == 200
    assert b"0001.jxl" in response.content


def test_detail_rejects_traversal(auth_client, library):
    response = auth_client.get("/folders/../etc/passwd")
    assert response.status_code == 404


def test_create_view_creates_folder(auth_client, library):
    response = auth_client.post(
        "/folders/new",
        {"kind": "movie", "title": "New", "year": 2002, "tmdb_id": 2, "copyright": "(c) Studio"},
    )
    assert response.status_code == 302
    assert (library / "New [2002][tmdb-2]").is_dir()


def test_search_without_token_shows_message(auth_client, library, settings):
    settings.TMDB_READ_TOKEN = ""
    response = auth_client.get("/folders/search", {"kind": "movie", "query": "Film"})
    assert b"TMDB_READ_TOKEN" in response.content


def test_search_uses_tmdb(auth_client, library, settings, monkeypatch):
    settings.TMDB_READ_TOKEN = "token"

    class FakeClient:
        def __init__(self, token):
            assert token == "token"

        def search_movies(self, query, year=None):
            return [MovieDetail(3, "Found", "Found", "1999-01-01")]

    monkeypatch.setattr("folders.views.TMDBClient", FakeClient)
    response = auth_client.get("/folders/search", {"kind": "movie", "query": "Found"})
    assert b"Found" in response.content


def test_hidden_folder_is_marked_in_list(auth_client, library):
    folder = library / "Hidden"
    folder.mkdir()
    write_metadata(folder, FolderMetadata(kind="other", title="Hidden", hidden=True))
    response = auth_client.get("/")
    assert b"hidden" in response.content


@pytest.mark.django_db
def test_create_series_enqueues_job(auth_client, library, settings, monkeypatch):
    settings.TMDB_READ_TOKEN = "token"
    monkeypatch.setattr("folders.views.TMDBClient", FakePosterClient)
    response = auth_client.post(
        "/folders/new",
        {
            "kind": "series",
            "title": "Show",
            "year": 2020,
            "tmdb_id": 2,
            "copyright": "",
            "cover_path": "/p.jpg",
        },
    )
    assert response.status_code == 302
    job = Job.objects.get(kind="folders.create_series")
    assert job.params["cover_path"] == "/p.jpg"
    assert not (library / "Show [2020][tmdb-2]").exists()


def test_create_movie_with_tmdb_cover(auth_client, library, settings, monkeypatch):
    settings.TMDB_READ_TOKEN = "token"
    monkeypatch.setattr("folders.views.TMDBClient", FakePosterClient)
    response = auth_client.post(
        "/folders/new",
        {
            "kind": "movie",
            "title": "Covered",
            "year": 2002,
            "tmdb_id": 2,
            "copyright": "",
            "cover_path": "/p.jpg",
        },
    )
    assert response.status_code == 302
    with Image.open(library / "Covered [2002][tmdb-2]" / ".cover.jxl") as cover:
        assert cover.size == (32, 48)


def test_create_page_lists_posters(auth_client, library, settings, monkeypatch):
    settings.TMDB_READ_TOKEN = "token"
    monkeypatch.setattr("folders.views.TMDBClient", FakePosterClient)
    response = auth_client.get(
        "/folders/new",
        {"kind": "movie", "title": "Covered", "year": 2002, "tmdb_id": 2},
    )
    assert b"/p.jpg" in response.content
    assert b"w185" in response.content


@pytest.mark.django_db
def test_add_season_enqueues_job(auth_client, library, settings):
    settings.TMDB_READ_TOKEN = "token"
    series = create_series(root=library, title="Show", year=2020, tmdb_id=2)
    response = auth_client.post(f"/folders/{quote(series.name)}/add-season", {"season_number": 2})
    assert response.status_code == 302
    assert Job.objects.filter(kind="folders.add_season").exists()
