import re

import pytest
from folders.services import create_movie
from importer.services import DEFAULT_TYPE_MAP, build_plan

PATTERN = re.compile(r" - (?P<index>\d{4})(?P<type>[A-Z]{0,2})$")


@pytest.fixture
def library(tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path / "wallpapers"
    settings.IMPORT_ROOT = tmp_path / "incoming"
    target = create_movie(root=settings.WALLPAPER_ROOT, title="Film", year=2001, tmdb_id=1)
    settings.IMPORT_ROOT.mkdir()
    (settings.IMPORT_ROOT / "Film - 0001.png").write_bytes(b"one")
    (settings.IMPORT_ROOT / "Film - 0002UM.png").write_bytes(b"two")
    (settings.IMPORT_ROOT / "notes.txt").write_text("skip")
    return target


def test_plan_maps_indexes_and_legacy_types(library, settings):
    plan = build_plan(
        source_root=settings.IMPORT_ROOT,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    assert [match.index for match in plan.matches] == [1, 2]
    assert plan.matches[1].flags == frozenset({"U", "M"})
    assert plan.matches[0].target_name == "Film [2001][tmdb-1] - 0001.jxl"
    assert [path.name for path in plan.unmatched] == ["notes.txt"]


def test_plan_reports_duplicate_index(library, settings):
    (settings.IMPORT_ROOT / "Film - 0001.jpg").write_bytes(b"dupe")
    plan = build_plan(
        source_root=settings.IMPORT_ROOT,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    assert plan.collisions


def test_plan_reports_existing_target(library, settings):
    (library / "Film [2001][tmdb-1] - 0001.jxl").write_bytes(b"exists")
    plan = build_plan(
        source_root=settings.IMPORT_ROOT,
        target=library,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    assert plan.collisions


def test_plan_requires_index_group(library, settings):
    with pytest.raises(ValueError):
        build_plan(
            source_root=settings.IMPORT_ROOT,
            target=library,
            pattern=re.compile(r"Film - \d{4}"),
            type_map=DEFAULT_TYPE_MAP,
        )


def test_preview_view_does_not_write(client, library, settings):
    response = client.post(
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
