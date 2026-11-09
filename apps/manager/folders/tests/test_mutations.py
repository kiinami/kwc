from urllib.parse import quote

import pytest

from filesystem.metadata import read_metadata
from folders.services import create_movie, delete_entity, set_cover, set_hidden
from jobs.models import Job
from jobs.worker import run_worker


@pytest.fixture
def library(tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path
    folder = create_movie(root=tmp_path, title="Film", year=2001, tmdb_id=1)
    (folder / "Film [2001][tmdb-1] - 0001.jxl").write_bytes(b"image")
    return folder


def path(value: str) -> str:
    return quote(value)


def test_delete_moves_to_trash(tmp_path, library):
    trash = tmp_path / ".trash"
    moved = delete_entity(folder=library, trash_root=trash)
    assert moved.is_dir()
    assert not library.exists()
    assert str(moved).startswith(str(trash))


def test_hide_sets_metadata(library):
    set_hidden(folder=library, hidden=True)
    assert read_metadata(library).hidden is True
    set_hidden(folder=library, hidden=False)
    assert read_metadata(library).hidden is False


def test_cover_copies_bytes(library):
    dest = set_cover(folder=library, image=library / "Film [2001][tmdb-1] - 0001.jxl")
    assert dest.read_bytes() == b"image"
    assert dest.name == ".cover.jxl"


def test_hide_view(auth_client, library):
    response = auth_client.post(f"/folders/{path('Film [2001][tmdb-1]')}/hide", {"hidden": "on"})
    assert response.status_code == 302
    assert read_metadata(library).hidden is True


def test_cover_view(auth_client, library):
    response = auth_client.post(
        f"/folders/{path('Film [2001][tmdb-1]')}/cover",
        {"image": "Film [2001][tmdb-1] - 0001.jxl"},
    )
    assert response.status_code == 302
    assert (library / ".cover.jxl").read_bytes() == b"image"


@pytest.mark.django_db
def test_delete_view_requires_confirmation(auth_client, library):
    response = auth_client.post(f"/folders/{path('Film [2001][tmdb-1]')}/delete", {"confirm": "wrong"})
    assert response.status_code == 200
    assert library.exists()


@pytest.mark.django_db
def test_delete_view_removes_folder_immediately(auth_client, library, settings):
    response = auth_client.post(f"/folders/{path('Film [2001][tmdb-1]')}/delete", {"confirm": "Film"})
    assert response.status_code == 302
    assert not library.exists()
    assert (settings.WALLPAPER_ROOT / ".trash").is_dir()
    assert not Job.objects.filter(kind="folders.delete").exists()


@pytest.mark.django_db
def test_rename_view_enqueues_job(auth_client, library):
    response = auth_client.post(
        f"/folders/{path('Film [2001][tmdb-1]')}/rename",
        {"new_title": "New Name", "new_year": 2002, "new_tmdb_id": 2, "confirm": "Film"},
    )
    assert response.status_code == 302
    run_worker(once=True)
    assert (library.parent / "New Name [2002][tmdb-2]").is_dir()
