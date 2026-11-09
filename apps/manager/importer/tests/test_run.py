import re

import pytest
from folders.services import create_movie
from importer.services import DEFAULT_TYPE_MAP, build_plan, run_plan
from jobs.worker import JobContext, run_worker
from PIL import Image

from filesystem.metadata import read_metadata
from media.metadata import read_image_metadata

PATTERN = re.compile(r" - (?P<index>\d{4})(?P<type>[A-Z]{0,2})$")


@pytest.fixture
def setup(tmp_path, settings):
    settings.WALLPAPER_ROOT = tmp_path / "wallpapers"
    settings.IMPORT_ROOT = tmp_path / "incoming"
    target = create_movie(root=settings.WALLPAPER_ROOT, title="Film", year=2001, tmdb_id=1)
    settings.IMPORT_ROOT.mkdir()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(settings.IMPORT_ROOT / "Film - 0001.png")
    return target


def test_import_writes_jxl_and_metadata(setup, settings):
    plan = build_plan(
        source_root=settings.IMPORT_ROOT,
        target=setup,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    result = run_plan(
        plan=plan,
        target=setup,
        pick_all=True,
        copyright="(c) Studio",
        ctx=JobContext.for_test(),
    )
    assert result == {"imported": 1}
    image = setup / "Film [2001][tmdb-1] - 0001+.jxl"
    assert image.is_file()
    metadata = read_image_metadata(image)
    assert metadata.copyright == "(c) Studio"
    assert metadata.generator == "import"
    assert metadata.source_sha256
    with Image.open(image) as opened:
        assert opened.size == (8, 8)


def test_import_can_leave_images_unpicked(setup, settings):
    plan = build_plan(
        source_root=settings.IMPORT_ROOT,
        target=setup,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    run_plan(plan=plan, target=setup, pick_all=False, copyright="", ctx=JobContext.for_test())
    assert (setup / "Film [2001][tmdb-1] - 0001.jxl").is_file()
    assert not list(setup.glob("*+.jxl"))


def test_import_refuses_collisions(setup, settings):
    (setup / "Film [2001][tmdb-1] - 0001.jxl").write_bytes(b"exists")
    plan = build_plan(
        source_root=settings.IMPORT_ROOT,
        target=setup,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    with pytest.raises(ValueError):
        run_plan(plan=plan, target=setup, pick_all=False, copyright="", ctx=JobContext.for_test())


@pytest.mark.django_db
def test_run_view_enqueues_job(auth_client, setup, settings):
    response = auth_client.post(
        "/importer/run",
        {
            "target": "Film [2001][tmdb-1]",
            "source": ".",
            "regex": PATTERN.pattern,
            "pick_all": "on",
        },
    )
    assert response.status_code == 302
    run_worker(once=True)
    assert (setup / "Film [2001][tmdb-1] - 0001+.jxl").is_file()


def test_copyright_comes_from_target_metadata(setup, settings):
    from filesystem.metadata import write_metadata

    metadata = read_metadata(setup)
    metadata.copyright = "(c) From metadata"
    write_metadata(setup, metadata)
    plan = build_plan(
        source_root=settings.IMPORT_ROOT,
        target=setup,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    run_plan(plan=plan, target=setup, pick_all=False, copyright=metadata.copyright, ctx=JobContext.for_test())
    assert read_image_metadata(setup / "Film [2001][tmdb-1] - 0001.jxl").copyright == "(c) From metadata"
