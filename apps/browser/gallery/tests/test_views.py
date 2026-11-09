from pathlib import Path
from urllib.parse import quote

import pillow_jxl  # noqa: F401  (registers the JXL plugin with Pillow)
import pytest
from PIL import Image

from filesystem.metadata import FolderMetadata, write_metadata


def jxl(path: Path, color: tuple[int, int, int] = (10, 20, 30)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), color).save(path, format="JXL", lossless=True)


@pytest.fixture
def library(tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path
    settings.KWC_BROWSER_CACHE_ROOT = tmp_path / "cache"
    film = tmp_path / "Film [2001][tmdb-1]"
    film.mkdir()
    write_metadata(film, FolderMetadata(kind="movie", title="Film", tmdb_id=1, copyright="(c) Studio"))
    jxl(film / "Film [2001][tmdb-1] - 0001+.jxl", (10, 20, 30))
    jxl(film / "Film [2001][tmdb-1] - 0002.jxl", (40, 50, 60))
    jxl(film / "Film [2001][tmdb-1] - 0002 [M].jxl", (70, 80, 90))
    jxl(film / ".cover.jxl", (1, 2, 3))

    hidden = tmp_path / "Hidden"
    hidden.mkdir()
    write_metadata(hidden, FolderMetadata(kind="other", title="Hidden", hidden=True))
    jxl(hidden / "Hidden - 0001.jxl")

    empty = tmp_path / "Empty"
    empty.mkdir()
    write_metadata(empty, FolderMetadata(kind="other", title="Empty"))

    broken = tmp_path / "Broken"
    broken.mkdir()
    (broken / ".metadata.toml").write_bytes(b'title = "\xff"')
    jxl(broken / "Broken - 0001.jxl")
    return tmp_path


def image_url(path: str) -> str:
    return "/i/" + quote(path)


def test_index_lists_visible_entities(client, library):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Film" in response.content
    assert b"Hidden" not in response.content
    assert b"Empty" not in response.content
    assert b"Broken" in response.content
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
    response = client.get(image_url("Film [2001][tmdb-1]/Film [2001][tmdb-1] - 0001+.jxl"))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jxl"
    assert b"".join(response.streaming_content)


def test_original_download_sets_attachment(client, library):
    response = client.get(image_url("Film [2001][tmdb-1]/Film [2001][tmdb-1] - 0001+.jxl") + "?download=1")
    assert response["Content-Disposition"].startswith("attachment")


def test_thumbnail_endpoint_is_cached_avif(client, library):
    response = client.get("/t/" + quote("Film [2001][tmdb-1]/Film [2001][tmdb-1] - 0001+.jxl"))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/avif"
    assert "immutable" in response["Cache-Control"]


def test_lens_derivative_is_avif(client, library):
    response = client.get("/l/" + quote("Film [2001][tmdb-1]/Film [2001][tmdb-1] - 0001+.jxl"))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/avif"


def test_lens_page_lists_variants(client, library):
    response = client.get("/view/" + quote("Film [2001][tmdb-1]") + "?index=2")
    assert response.status_code == 200
    assert b"#2" in response.content
    assert b"0002 [M].jxl" in response.content
    assert b"(c) Studio" in response.content


def test_downloads_json_lists_curated_images(client, library):
    response = client.get("/downloads.json?curated=1")
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["images"]]
    assert names == ["Film [2001][tmdb-1] - 0001+.jxl"]


def test_downloads_json_lists_all_images(client, library):
    response = client.get("/downloads.json?curated=0")
    names = [item["name"] for item in response.json()["images"]]
    assert len(names) == 4
    assert all(not name.startswith("Hidden") for name in names)


def test_head_supports_download_preflight(client, library):
    response = client.head(image_url("Film [2001][tmdb-1]/Film [2001][tmdb-1] - 0001+.jxl"))
    assert response.status_code == 200


def test_folder_page_has_download_controls(client, library):
    response = client.get("/browse/" + quote("Film [2001][tmdb-1]") + "?curated=0")
    assert b"data-download" in response.content
    assert b"download.js" in response.content
    assert b"zip.js" in response.content
    assert b"data-max-bytes" in response.content


def test_hidden_and_trash_images_are_rejected(client, library):
    hidden = "Hidden/Hidden - 0001.jxl"
    assert client.get(image_url(hidden)).status_code == 404
    assert client.get("/t/" + quote(hidden)).status_code == 404
    assert client.get("/i/" + quote(".trash/Old/Old - 0001.jxl")).status_code == 404


def test_traversal_is_rejected(client, library):
    assert client.get("/i/../etc/passwd").status_code == 404
    assert client.get("/browse/../etc").status_code == 404


def test_hidden_folder_is_not_browsable(client, library):
    assert client.get("/browse/Hidden").status_code == 404
