import os
from datetime import UTC, datetime
from pathlib import Path

from filesystem.metadata import FolderMetadata, write_metadata
from filesystem.ordering import sort_entities
from filesystem.scan import scan_archive


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def _set_mtime(path: Path, when: datetime) -> None:
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def _tree(root: Path) -> Path:
    old = root / "Old [1990][tmdb-1]"
    old.mkdir()
    write_metadata(old, FolderMetadata(original_title="Old", release_date="1990-01-01"))
    _touch(old / "Old [1990][tmdb-1] - 0001.jxl")

    new = root / "New [2020][tmdb-2]"
    new.mkdir()
    write_metadata(new, FolderMetadata(original_title="New", release_date="2020-01-01"))
    _touch(new / "New [2020][tmdb-2] - 0001.jxl")

    show = root / "Show [2010][tmdb-3]"
    show.mkdir()
    write_metadata(
        show,
        FolderMetadata(original_title="Show", first_release_date="2010-01-01", last_release_date="2022-01-01"),
    )
    _touch(show / "S01" / "E01" / "Show [2010][tmdb-3] - S01E01 - 0001.jxl")

    other = root / "Extra"
    _touch(other / "Extra - 0001.jxl")
    _set_mtime(other / "Extra - 0001.jxl", datetime(2024, 6, 1, tzinfo=UTC))

    return root


def test_entities_are_sorted_newest_first_across_kinds(tmp_path):
    archive = scan_archive(_tree(tmp_path))
    entities = sort_entities([*archive.movies, *archive.series, *archive.others])
    assert [entity.title for entity in entities] == ["Extra", "Show", "New", "Old"]


def test_older_added_other_sorts_last(tmp_path):
    root = tmp_path
    missing = root / "Undated"
    missing.mkdir()
    _touch(missing / "Undated - 0001.jxl")
    _set_mtime(missing / "Undated - 0001.jxl", datetime(1980, 1, 1, tzinfo=UTC))

    movie = root / "Movie [2020][tmdb-1]"
    movie.mkdir()
    write_metadata(movie, FolderMetadata(release_date="2020-01-01"))
    _touch(movie / "Movie [2020][tmdb-1] - 0001.jxl")

    archive = scan_archive(root)
    entities = sort_entities([*archive.movies, *archive.others])
    assert entities[0].title == "Movie"
    assert entities[-1].title == "Undated"
