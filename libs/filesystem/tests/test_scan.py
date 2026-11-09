from pathlib import Path

from filesystem.scan import scan_archive, scan_entity


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def make_tree(root: Path) -> Path:
    movie = root / "Film [2001][tmdb-1]"
    for name in (
        ".cover.jxl",
        ".metadata.toml",
        "Film [2001][tmdb-1] - 0002 [M].jxl",
        "Film [2001][tmdb-1] - 0001+.jxl",
        "Film [2001][tmdb-1] - 0002.jxl",
        "bad.jxl",
    ):
        _touch(movie / name)
    (movie / ".metadata.toml").write_text('original_title = "Original Film"\nrelease_date = "2001-01-01"\n')

    series = root / "Show [2020][tmdb-2]"
    (series / ".metadata.toml").parent.mkdir(parents=True, exist_ok=True)
    (series / ".metadata.toml").write_text(
        'original_title = "Original Show"\nfirst_release_date = "2020-01-01"\nlast_release_date = "2021-01-01"\n'
    )
    episode = series / "S01" / "E01"
    _touch(episode / "Show [2020][tmdb-2] - S01E01 - 0001.jxl")

    other = root / "Other"
    _touch(other / ".metadata.toml")
    _touch(other / "Other - 0001.jxl")

    _touch(root / "Empty" / ".metadata.toml")

    broken = root / "ZOther"
    _touch(broken / "ZOther - 0001.jxl")
    (broken / ".metadata.toml").write_text("not = [valid")

    _touch(root / ".hidden" / "Thing" / "Thing - 0001.jxl")
    _touch(root / ".trash" / "Old" / "Old - 0001.jxl")
    return root


def test_scan_orders_images_and_finds_cover(tmp_path):
    archive = scan_archive(make_tree(tmp_path))
    movie = archive.movies[0]
    assert [i.name for i in movie.images] == [
        "Film [2001][tmdb-1] - 0001+.jxl",
        "Film [2001][tmdb-1] - 0002.jxl",
        "Film [2001][tmdb-1] - 0002 [M].jxl",
    ]
    assert movie.cover is not None
    assert movie.metadata.original_title == "Original Film"
    assert movie.metadata.release_date == "2001-01-01"


def test_scan_skips_dotfiles_trash_and_bad_names(tmp_path):
    archive = scan_archive(make_tree(tmp_path))
    assert all(".trash" not in str(e.path) for e in archive.movies + archive.series + archive.others)
    assert all(".hidden" not in str(e.path) for e in archive.movies + archive.series + archive.others)
    assert len(archive.movies[0].images) == 3


def test_malformed_metadata_falls_back_to_folder_name(tmp_path):
    archive = scan_archive(make_tree(tmp_path))
    broken = next(entity for entity in archive.others if entity.path.name == "ZOther")
    assert broken.metadata is None
    assert broken.title == "ZOther"


def test_series_structure_and_episode_images(tmp_path):
    archive = scan_archive(make_tree(tmp_path))
    series = archive.series[0]
    assert series.title == "Show"
    assert [season.season for season in series.children] == [1]
    episode = series.children[0].children[0]
    assert episode.kind == "episode"
    assert episode.episode == "E01"
    assert episode.images[0].index == 1


def test_scan_entity_reads_a_single_folder(tmp_path):
    entity = scan_entity(make_tree(tmp_path) / "Film [2001][tmdb-1]")
    assert entity.kind == "movie"
    assert entity.title == "Film"
    assert len(entity.images) == 3


def test_scan_skips_symlinked_directories(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    _touch(outside / "Outside [2001][tmdb-1]" / ".metadata.toml")
    (outside / "Outside [2001][tmdb-1]" / ".metadata.toml").write_text('kind = "movie"\ntitle = "Outside"\n')
    root = tmp_path / "root"
    root.mkdir()
    (root / "Link").symlink_to(outside / "Outside [2001][tmdb-1]", target_is_directory=True)
    archive = scan_archive(root)
    assert archive.movies == ()
    assert archive.series == ()
    assert archive.others == ()
