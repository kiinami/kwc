import re

import pytest
from folders.services import create_movie
from importer.services import DEFAULT_TYPE_MAP, build_plan

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


def test_browse_lists_folders(auth_client, library, source):
    (source / "legacy" / "nested").mkdir(parents=True)
    response = auth_client.get("/importer/browse")
    assert response.status_code == 200
    assert b"legacy" in response.content
    nested = auth_client.get("/importer/browse", {"path": "legacy"})
    assert b"nested" in nested.content


def test_browse_rejects_traversal(auth_client, library, source):
    assert auth_client.get("/importer/browse", {"path": "../etc"}).status_code == 404
