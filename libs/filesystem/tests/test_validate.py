from pathlib import Path

from filesystem.validate import validate_archive


def _touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def broken_tree(root: Path) -> Path:
    film = root / "Film [2001][tmdb-1]"
    _touch(film / ".metadata.toml", 'original_title = "Film"\nrelease_date = "2001-01-01"\n')
    _touch(film / "Film [2001][tmdb-1] - 0001.jxl")
    _touch(film / "Film [2001][tmdb-1] - 0001+.jxl")
    _touch(film / "bad.jxl")
    _touch(film / "Film [2001][tmdb-1] - 10000.jxl")

    show = root / "Show [2020][tmdb-2]"
    _touch(
        show / ".metadata.toml",
        'original_title = "Show"\nfirst_release_date = "2020-01-01"\nlast_release_date = "2021-01-01"\n',
    )
    _touch(show / "S01" / ".metadata.toml", 'first_release_date = "2020-01-01"\nlast_release_date = "2021-01-01"\n')
    _touch(show / "S01" / "E01" / "Show [2020][tmdb-2] - S01E01 - 0001.jxl")
    _touch(show / "E02" / "Show [2020][tmdb-2] - S01E02 - 0001.jxl")

    empty = root / "Empty"
    _touch(empty / ".metadata.toml")
    _touch(empty / ".cover.jxl")

    _touch(root / "Broken [1999][tmdb-3]" / ".metadata.toml", "not = [valid")
    _touch(root / "Bad [Folder]" / ".metadata.toml")
    missing = root / "NoMeta [2000][tmdb-4]"
    _touch(missing / "NoMeta [2000][tmdb-4] - 0001.jxl")
    return root


def clean_tree(root: Path) -> Path:
    film = root / "Film [2001][tmdb-1]"
    _touch(film / ".metadata.toml", 'original_title = "Film"\nrelease_date = "2001-01-01"\n')
    _touch(film / "Film [2001][tmdb-1] - 0001.jxl")

    show = root / "Show [2020][tmdb-2]"
    _touch(
        show / ".metadata.toml",
        'original_title = "Show"\nfirst_release_date = "2020-01-01"\nlast_release_date = "2021-01-01"\n',
    )
    _touch(show / "S01" / ".metadata.toml", 'first_release_date = "2020-01-01"\nlast_release_date = "2021-01-01"\n')
    _touch(show / "S01" / "E01" / "Show [2020][tmdb-2] - S01E01 - 0001.jxl")

    other = root / "Other"
    _touch(other / ".metadata.toml")
    _touch(other / "Other - 0001.jxl")
    return root


def test_reports_duplicate_index(tmp_path):
    codes = {issue.code for issue in validate_archive(broken_tree(tmp_path))}
    assert "duplicate-index" in codes


def test_reports_mixed_layout(tmp_path):
    codes = {issue.code for issue in validate_archive(broken_tree(tmp_path))}
    assert "mixed-layout" in codes


def test_reports_all_structural_problems(tmp_path):
    codes = {issue.code for issue in validate_archive(broken_tree(tmp_path))}
    assert {
        "unparsed-folder",
        "unparsed-file",
        "duplicate-index",
        "mixed-layout",
        "missing-metadata",
        "orphan-cover",
        "metadata-invalid",
        "index-out-of-range",
    } <= codes


def test_clean_archive_has_no_issues(tmp_path):
    assert validate_archive(clean_tree(tmp_path)) == []


def test_missing_root_is_clean(tmp_path):
    assert validate_archive(tmp_path / "nope") == []
