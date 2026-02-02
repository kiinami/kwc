from __future__ import annotations

from pathlib import Path

import pytest

from choose.models import FolderProgress, ImageDecision
from choose.services import ingest_inbox_folder, list_gallery_images, load_folder_context
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

	from choose import services

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

	from choose import services

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


def test_list_gallery_images_groups_series_by_season_episode(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Series (2024)"
	folder.mkdir()
	(folder / "Series S01E01.jpg").write_bytes(b"a")
	(folder / "Series S01E02.jpg").write_bytes(b"b")
	(folder / "Series S01EIN.jpg").write_bytes(b"c")
	(folder / "Series S02E01.jpg").write_bytes(b"d")
	(folder / "General.jpg").write_bytes(b"e")

	context = list_gallery_images("Series (2024)")

	# Check we have sections
	assert len(context.sections) == 5
	
	# Check section ordering and titles
	assert context.sections[0]["title"] == "General"
	assert len(context.sections[0]["images"]) == 1
	
	assert context.sections[1]["title"] == "Season 1 Intro"
	assert len(context.sections[1]["images"]) == 1
	
	assert context.sections[2]["title"] == "Season 1 Episode 1"
	assert len(context.sections[2]["images"]) == 1
	
	assert context.sections[3]["title"] == "Season 1 Episode 2"
	assert len(context.sections[3]["images"]) == 1

	assert context.sections[4]["title"] == "Season 2 Episode 1"
	assert len(context.sections[4]["images"]) == 1


def test_list_gallery_images_single_section_for_movies(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Movie (2024)"
	folder.mkdir()
	(folder / "frame01.jpg").write_bytes(b"a")
	(folder / "frame02.jpg").write_bytes(b"b")

	context = list_gallery_images("Movie (2024)")

	# All images should be in the "General" section
	assert len(context.sections) == 1
	assert context.sections[0]["title"] == "General"
	assert len(context.sections[0]["images"]) == 2


def test_list_gallery_images_sections_have_season_episode_and_choose_url(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Series (2024)"
	folder.mkdir()
	(folder / "Series S01E01.jpg").write_bytes(b"a")
	(folder / "Series S02EIN.jpg").write_bytes(b"b")
	(folder / "General.jpg").write_bytes(b"c")

	context = list_gallery_images("Series (2024)")

	# Check General section
	general_section = context.sections[0]
	assert general_section["season"] == ""
	assert general_section["episode"] == ""
	assert "/Series%20(2024)/" in general_section["choose_url"]
	
	# Check Season 1 Episode 1 section
	s1e1_section = context.sections[1]
	assert s1e1_section["season"] == "01"
	assert s1e1_section["episode"] == "01"
	assert "season=01" in s1e1_section["choose_url"]
	assert "episode=01" in s1e1_section["choose_url"]
	
	# Check Season 2 Intro section
	intro_section = context.sections[2]
	assert intro_section["season"] == "02"
	assert intro_section["episode"] == "IN"
	assert "season=02" in intro_section["choose_url"]
	assert "episode=IN" in intro_section["choose_url"]


def test_load_folder_context_filters_by_season(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Series"
	folder.mkdir()
	(folder / "Series S01E01.jpg").write_bytes(b"a")
	(folder / "Series S01E02.jpg").write_bytes(b"b")
	(folder / "Series S02E01.jpg").write_bytes(b"c")
	(folder / "General.jpg").write_bytes(b"d")

	context = load_folder_context("Series", season="01")

	# Should only have season 1 episodes
	assert len(context.images) == 2
	assert context.images[0]["name"] == "Series S01E01.jpg"
	assert context.images[1]["name"] == "Series S01E02.jpg"


def test_load_folder_context_filters_by_season_and_episode(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Series"
	folder.mkdir()
	(folder / "Series S01E01.jpg").write_bytes(b"a")
	(folder / "Series S01E02.jpg").write_bytes(b"b")
	(folder / "Series S02E01.jpg").write_bytes(b"c")

	context = load_folder_context("Series", season="01", episode="02")

	# Should only have S01E02
	assert len(context.images) == 1
	assert context.images[0]["name"] == "Series S01E02.jpg"


def test_load_folder_context_filters_general_section(wallpapers_dir: Path) -> None:
	folder = wallpapers_dir / "Series"
	folder.mkdir()
	(folder / "Series S01E01.jpg").write_bytes(b"a")
	(folder / "General.jpg").write_bytes(b"b")

	# Filter for General section (no season, no episode)
	context = load_folder_context("Series", season="", episode="")

	# Should only have General.jpg
	assert len(context.images) == 1
	assert context.images[0]["name"] == "General.jpg"


@pytest.fixture()
def ingest_dirs(tmp_path: Path, settings) -> Path:
    settings.WALLPAPERS_FOLDER = tmp_path / "wallpapers"
    settings.EXTRACTION_FOLDER = tmp_path / "extraction"
    settings.DISCARD_FOLDER = tmp_path / "discard"
    settings.EXTRACT_IMAGE_PATTERN = "{title} 〜 {counter}"
    
    settings.WALLPAPERS_FOLDER.mkdir()
    settings.EXTRACTION_FOLDER.mkdir()
    settings.DISCARD_FOLDER.mkdir()
    
    return tmp_path


def test_ingest_copies_cover_image(ingest_dirs: Path, settings) -> None:
    folder_name = "New Series (2025)"
    inbox_folder = Path(settings.EXTRACTION_FOLDER) / folder_name
    inbox_folder.mkdir()
    
    # create cover image
    cover_file = inbox_folder / ".cover.png"
    cover_file.write_bytes(b"fake cover content")
    
    # create an image file and a decision
    image_file = inbox_folder / "image.jpg"
    image_file.write_bytes(b"fake image content")
    
    ImageDecision.objects.create(
        folder=folder_name,
        filename="image.jpg",
        decision=ImageDecision.DECISION_KEEP
    )
    
    ingest_inbox_folder(folder_name)
    
    # Check if cover image was copied to library
    lib_folder = Path(settings.WALLPAPERS_FOLDER) / folder_name
    lib_cover = lib_folder / ".cover.png"
    
    assert lib_folder.exists()
    assert lib_cover.exists()
    assert lib_cover.read_bytes() == b"fake cover content"
    
    # Check if image was moved (renamed)
    files = list(lib_folder.glob("*.jpg"))
    assert len(files) == 1
    
    assert not inbox_folder.exists()


def test_ingest_does_not_overwrite_existing_cover(ingest_dirs: Path, settings) -> None:
    folder_name = "Existing Series (2025)"
    inbox_folder = Path(settings.EXTRACTION_FOLDER) / folder_name
    inbox_folder.mkdir()
    
    # inbox cover
    (inbox_folder / ".cover.png").write_bytes(b"new cover")
    
    # existing library folder with cover
    lib_folder = Path(settings.WALLPAPERS_FOLDER) / folder_name
    lib_folder.mkdir()
    (lib_folder / ".cover.png").write_bytes(b"old cover")
    
    # create image and decision
    (inbox_folder / "image.jpg").write_bytes(b"img")
    ImageDecision.objects.create(
        folder=folder_name,
        filename="image.jpg",
        decision=ImageDecision.DECISION_KEEP
    )
    
    ingest_inbox_folder(folder_name)
    
    assert (lib_folder / ".cover.png").read_bytes() == b"old cover"
    assert not inbox_folder.exists()
