from pathlib import Path

from filesystem.metadata import FolderMetadata, write_metadata


def touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_doctor_lists_issues(auth_client, tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path
    folder = tmp_path / "Film [2001][tmdb-1]"
    folder.mkdir()
    write_metadata(folder, FolderMetadata(kind="movie", title="Film", tmdb_id=1))
    touch(folder / "Film [2001][tmdb-1] - 0001.jxl")
    touch(folder / "Film [2001][tmdb-1] - 0001+.jxl")

    response = auth_client.get("/folders/doctor")
    assert response.status_code == 200
    assert b"duplicate-index" in response.content


def test_doctor_clean_archive(auth_client, tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path
    response = auth_client.get("/folders/doctor")
    assert b"No issues" in response.content
