from __future__ import annotations

from pathlib import Path

import pytest

from choose.models import FolderProgress, ImageDecision
from choose.services import load_folder_context, list_gallery_images
from choose.utils import wallpapers_root

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture()
def wallpapers_dir(tmp_path: Path, settings) -> Path:
	settings.WALLPAPERS_FOLDER = tmp_path
	return tmp_path


def test_list_gallery_images_returns_metadata(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Movie (2024)"
	folder.mkdir()
	(folder / ".cover.jpg").write_bytes(b"cover")
	(folder / "frame01.jpg").write_bytes(b"a")
	(folder / "frame02.jpg").write_bytes(b"b")

	context = list_gallery_images("Movie (2024)")

	assert context.folder == "Movie (2024)"
	assert context.title == "Movie"
	assert context.year == "2024"
	assert context.year_raw == 2024
	assert context.cover_url is not None
	assert context.cover_thumb_url is not None
	assert len(context.images) == 2
	assert context.images[0]["name"].endswith(".jpg")
	assert context.choose_url
	assert context.root == str(wallpapers_dir)


def test_list_gallery_images_handles_permission_error(monkeypatch: pytest.MonkeyPatch, wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Show"
	folder.mkdir()

	import choose.services as services

	def deny(_path: Path) -> list[str]:
		raise PermissionError("denied")

	monkeypatch.setattr(services, "list_image_files", deny)

	context = list_gallery_images("Show")

	assert context.images == []


def test_load_folder_context_missing_folder(wallpapers_dir: Path) -> None:
	with pytest.raises(FileNotFoundError):
		load_folder_context("Absent")


def test_load_folder_context_permission_error(monkeypatch: pytest.MonkeyPatch, wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Clip"
	folder.mkdir()

	import choose.services as services

	def deny(_path: Path) -> list[str]:
		raise PermissionError("nope")

	monkeypatch.setattr(services, "list_image_files", deny)

	context = load_folder_context("Clip")

	assert context.images == []
	assert context.selected_index == -1
	assert context.selected_image_url == ""
	assert context.root == str(wallpapers_dir)
	assert context.path == str(folder)


def test_load_folder_context_resume_progress(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Episode"
	folder.mkdir()
	for name in ("frame01.jpg", "frame02.jpg", "frame03.jpg"):
		(folder / name).write_bytes(b"x")

	ImageDecision.objects.create(
		folder="Episode",
		filename="frame01.jpg",
		decision=ImageDecision.DECISION_KEEP,
	)

	FolderProgress.objects.create(
		folder="Episode",
		last_classified_name="frame01.jpg",
		keep_count=1,
	)

	context = load_folder_context("Episode")

	assert context.images[0]["decision"] == ImageDecision.DECISION_KEEP
	assert context.selected_index == 1
	assert context.selected_image_name == "frame02.jpg"
	assert context.selected_image_url


def test_load_folder_context_empty_folder(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Empty"
	folder.mkdir()

	context = load_folder_context("Empty")

	assert context.images == []
	assert context.selected_index == -1
	assert context.selected_image_name == ""
	assert context.selected_image_url == ""
	assert context.root == str(wallpapers_root())
