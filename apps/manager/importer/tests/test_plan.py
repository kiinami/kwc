import re

import pytest

from folders.services import create_movie
from importer.services import DEFAULT_TYPE_MAP, build_plan, detect_pattern

PATTERN = re.compile(r" - (?P<index>\d{4})(?P<type>[A-Z]{0,2})$")


@pytest.fixture
def library(tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path / "wallpapers"
    return create_movie(root=settings.WALLPAPER_ROOT, title="Film", year=2001, tmdb_id=1)


@pytest.fixture
def source(tmp_path, settings):
    settings.IMPORT_ROOT = tmp_path / "import"
    folder = settings.IMPORT_ROOT
    folder.mkdir()
    (folder / "Film - 0001.png").write_bytes(b"one")
    (folder / "Film - 0002UM.png").write_bytes(b"two")
    (folder / "notes.txt").write_text("skip")
    return folder


def test_plan_maps_indexes_and_legacy_types(library, source):
    plan = build_plan(
        source_root=source,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    assert [match.index for match in plan.matches] == [1, 2]
    assert plan.matches[1].flags == frozenset({"U", "M"})
    assert plan.matches[0].target_name == "Film [2001][tmdb-1] - 0001.jxl"
    assert [path.name for path in plan.unmatched] == ["notes.txt"]


def test_plan_reports_duplicate_index(library, source):
    (source / "Film - 0001.jpg").write_bytes(b"dupe")
    plan = build_plan(
        source_root=source,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    assert plan.collisions


def test_plan_reports_existing_target(library, source):
    (library / "Film [2001][tmdb-1] - 0001.jxl").write_bytes(b"exists")
    plan = build_plan(
        source_root=source,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    assert plan.collisions


def test_plan_maps_edited_to_alternate(library, source):
    (source / "Film - 0003E.png").write_bytes(b"edited")
    plan = build_plan(
        source_root=source,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    match = next(item for item in plan.matches if item.source.name == "Film - 0003E.png")
    assert match.flags == frozenset({"A"})
    assert match.target_name == "Film [2001][tmdb-1] - 0003 [A].jxl"


def test_plan_reduced_becomes_base_and_old_base_becomes_upscaled(library, source):
    (source / "Film - 0001R.png").write_bytes(b"reduced")
    plan = build_plan(
        source_root=source,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    reduced = next(item for item in plan.matches if item.source.name == "Film - 0001R.png")
    old_base = next(item for item in plan.matches if item.source.name == "Film - 0001.png")
    assert reduced.flags == frozenset()
    assert reduced.target_name == "Film [2001][tmdb-1] - 0001.jxl"
    assert old_base.flags == frozenset({"U"})
    assert old_base.target_name == "Film [2001][tmdb-1] - 0001 [U].jxl"


def test_plan_reduced_without_base_becomes_base(library, source):
    (source / "Film - 0002R.png").write_bytes(b"reduced")
    plan = build_plan(
        source_root=source,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    reduced = next(item for item in plan.matches if item.source.name == "Film - 0002R.png")
    assert reduced.target_name == "Film [2001][tmdb-1] - 0002.jxl"


def test_plan_reduced_mobile_swaps_mobile_variant(library, source):
    (source / "Film - 0003M.png").write_bytes(b"mobile")
    (source / "Film - 0003RM.png").write_bytes(b"reduced mobile")
    plan = build_plan(
        source_root=source,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    reduced = next(item for item in plan.matches if item.source.name == "Film - 0003RM.png")
    mobile = next(item for item in plan.matches if item.source.name == "Film - 0003M.png")
    assert reduced.target_name == "Film [2001][tmdb-1] - 0003 [M].jxl"
    assert mobile.target_name == "Film [2001][tmdb-1] - 0003 [UM].jxl"


def test_plan_reduced_conflicts_with_upscaled(library, source):
    (source / "Film - 0001R.png").write_bytes(b"reduced")
    (source / "Film - 0001U.png").write_bytes(b"upscaled")
    plan = build_plan(
        source_root=source,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    assert plan.collisions


def test_plan_requires_index_group(library, source):
    with pytest.raises(ValueError):
        build_plan(
            source_root=source,
            target=library,
            pattern=re.compile(r"Film - \d{4}"),
            type_map=DEFAULT_TYPE_MAP,
        )


def test_preview_view_does_not_write(auth_client, library, source):
    response = auth_client.post(
        "/importer",
        {
            "target": "Film [2001][tmdb-1]",
            "source": ".",
            "regex": PATTERN.pattern,
            "pick_all": "on",
        },
    )
    assert response.status_code == 200
    assert b"0002 [UM].jxl" in response.content
    assert not (library / "Film [2001][tmdb-1] - 0001.jxl").exists()


def test_detect_button_bypasses_browser_validation(auth_client, library, source):
    response = auth_client.get("/importer")
    assert b"formnovalidate" in response.content


def test_detect_pattern_proposes_index_and_type(source):
    (source / "Film - 0003E.png").write_bytes(b"edited")
    detected = detect_pattern(source)
    assert detected is not None
    assert detected.regex == r"(?P<index>\d{4})(?P<type>[A-Z]{0,3})$"
    assert (detected.matched, detected.total) == (3, 3)
    assert ("Film - 0002UM.png", 2, "UM") in detected.samples


def test_detect_pattern_returns_none_without_images(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect_pattern(empty) is None


def test_detect_view_prefills_regex(auth_client, library, source):
    response = auth_client.post(
        "/importer",
        {"action": "detect", "source": ".", "target": "Film [2001][tmdb-1]"},
    )
    assert response.status_code == 200
    detected = response.context["detected"]
    assert detected is not None
    assert response.context["form"]["regex"].value() == detected.regex
    assert b"Detected from 2 / 2 image filenames" in response.content


def test_browse_lists_folders(auth_client, library, source):
    (source / "legacy" / "nested").mkdir(parents=True)
    response = auth_client.get("/importer/browse")
    assert response.status_code == 200
    assert b"legacy" in response.content
    nested = auth_client.get("/importer/browse", {"path": "legacy"})
    assert b"nested" in nested.content


def test_browse_rejects_traversal(auth_client, library, source):
    assert auth_client.get("/importer/browse", {"path": "../etc"}).status_code == 404
