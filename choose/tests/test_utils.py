from __future__ import annotations

from pathlib import Path

import pytest

from choose.utils import (
	MediaFolder,
	list_media_folders,
	parse_folder_name,
	parse_title_year_from_folder,
	validate_folder_name,
)
from kwc.utils.files import cache_token


@pytest.fixture()
def temp_wallpapers_dir(tmp_path: Path) -> Path:
	return tmp_path


def _make_folder(root: Path, name: str, files: dict[str, bytes] | None = None) -> Path:
	dir_path = root / name
	dir_path.mkdir(parents=True, exist_ok=True)
	files = files or {}
	for rel, data in files.items():
		file_path = dir_path / rel
		file_path.write_bytes(data)
	return dir_path


def test_validate_folder_name_accepts_simple_names() -> None:
	assert validate_folder_name("Movie 2024") == "Movie 2024"


def test_validate_folder_name_rejects_hidden_folder() -> None:
	with pytest.raises(ValueError):
		validate_folder_name(".hidden")


def test_validate_folder_name_rejects_traversal() -> None:
	with pytest.raises(ValueError):
		validate_folder_name("../secret")


def test_parse_folder_name_with_year() -> None:
	title, year = parse_folder_name("My Film (2022)")
	assert title == "My Film"
	assert year == 2022


def test_parse_folder_name_without_year() -> None:
	title, year = parse_folder_name("Plain Title")
	assert title == "Plain Title"
	assert year is None


def test_parse_title_year_from_folder_returns_raw_year() -> None:
	title, year_raw = parse_title_year_from_folder("Movie (2024)")
	assert title == "Movie"
	assert year_raw == 2024


def test_list_media_folders_collects_metadata(temp_wallpapers_dir: Path) -> None:
	_make_folder(
		temp_wallpapers_dir,
		"Show (1999)",
		{
			"frame1.jpg": b"x",
			".cover.jpg": b"y",
		},
	)
	_make_folder(
		temp_wallpapers_dir,
		"Another", {"still.png": b"z"}
	)

	entries, root = list_media_folders(root=temp_wallpapers_dir)
	assert root == temp_wallpapers_dir
	assert len(entries) == 2

	entries_by_name = {entry['name']: entry for entry in entries}
	sample: MediaFolder = entries_by_name['Show (1999)']
	assert "name" in sample
	assert "cover_url" in sample
	assert "cover_thumb_url" in sample
	assert sample['year'] == '1999'
	assert sample['year_raw'] == 1999
	assert isinstance(sample['mtime'], int)


def test_cache_token_is_stable(temp_wallpapers_dir: Path) -> None:
	file_path = temp_wallpapers_dir / "sample.txt"
	file_path.write_text("hello")

	first = cache_token(file_path)
	second = cache_token(file_path)
	assert first == second
