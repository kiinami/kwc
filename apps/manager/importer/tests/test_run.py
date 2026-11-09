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
    settings.IMPORT_ROOT = tmp_path / "import"
    target = create_movie(
        root=settings.WALLPAPER_ROOT,
        title="Film",
        year=2001,
        tmdb_id=1,
        original_title="Original Film",
        release_date="2001-01-01",
    )
    source = settings.IMPORT_ROOT / "incoming"
    source.mkdir(parents=True)
    Image.new("RGB", (8, 8), (1, 2, 3)).save(source / "Film - 0001.png")
    return target, source


def test_import_writes_jxl_and_metadata(setup, settings):
    target, source = setup
    plan = build_plan(
        source_root=source,
        target=target,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    result = run_plan(
        plan=plan,
        target=target,
        pick_all=True,
        copyright="(c) Studio",
        ctx=JobContext.for_test(),
    )
    assert result == {"imported": 1}
    image = target / "Film [2001][tmdb-1] - 0001+.jxl"
    assert image.is_file()
    metadata = read_image_metadata(image)
    assert metadata.copyright == "(c) Studio"
    assert metadata.generator == "import"
    assert metadata.source_sha256
    with Image.open(image) as opened:
        assert opened.size == (8, 8)


def test_import_can_leave_images_unpicked(setup, settings):
    target, source = setup
    plan = build_plan(
        source_root=source,
        target=target,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    run_plan(plan=plan, target=target, pick_all=False, copyright="", ctx=JobContext.for_test())
    assert (target / "Film [2001][tmdb-1] - 0001.jxl").is_file()
    assert not list(target.glob("*+.jxl"))


def test_import_swaps_reduced_into_base(setup, settings):
    target, source = setup
    Image.new("RGB", (8, 8), (9, 9, 9)).save(source / "Film - 0001R.png")
    plan = build_plan(
        source_root=source,
        target=target,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    run_plan(plan=plan, target=target, pick_all=False, copyright="", ctx=JobContext.for_test())
    with Image.open(target / "Film [2001][tmdb-1] - 0001.jxl") as base:
        base.load()
        assert base.getpixel((0, 0)) == (9, 9, 9)
    with Image.open(target / "Film [2001][tmdb-1] - 0001 [U].jxl") as upscaled:
        upscaled.load()
        assert upscaled.getpixel((0, 0)) == (1, 2, 3)


def test_import_refuses_collisions(setup, settings):
    target, source = setup
    (target / "Film [2001][tmdb-1] - 0001.jxl").write_bytes(b"exists")
    plan = build_plan(
        source_root=source,
        target=target,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    with pytest.raises(ValueError):
        run_plan(plan=plan, target=target, pick_all=False, copyright="", ctx=JobContext.for_test())


@pytest.mark.django_db
def test_run_view_enqueues_job(auth_client, setup, settings):
    target, _source = setup
    preview = auth_client.post(
        "/importer",
        {
            "target": "Film [2001][tmdb-1]",
            "source": "incoming",
            "regex": PATTERN.pattern,
            "pick_all": "on",
        },
    )
    assert preview.status_code == 200
    response = auth_client.post(
        "/importer/run",
        {
            "target": "Film [2001][tmdb-1]",
            "source": "incoming",
            "regex": PATTERN.pattern,
            "pick_all": "on",
        },
    )
    assert response.status_code == 302
    run_worker(once=True)
    assert (target / "Film [2001][tmdb-1] - 0001+.jxl").is_file()


def test_copyright_comes_from_target_metadata(setup, settings):
    target, source = setup
    from filesystem.metadata import write_metadata

    metadata = read_metadata(target)
    metadata.copyright = "(c) From metadata"
    write_metadata(target, metadata)
    plan = build_plan(
        source_root=source,
        target=target,
        pattern=PATTERN,
        type_map=DEFAULT_TYPE_MAP,
    )
    run_plan(plan=plan, target=target, pick_all=False, copyright=metadata.copyright, ctx=JobContext.for_test())
    assert read_image_metadata(target / "Film [2001][tmdb-1] - 0001.jxl").copyright == "(c) From metadata"
