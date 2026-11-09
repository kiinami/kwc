from pathlib import Path

import pytest

from filesystem.naming import ImageName, NameScope
from filesystem.operations import IndexExhausted, PathEscape, next_index, rename_image, resolve_under, toggle_pick
from filesystem.scan import ImageFile, scan_entity

SCOPE = NameScope("Film", 2001, 1)


def make_movie(root: Path, indexes: tuple[int, ...] = (1, 7)):
    folder = root / "Film [2001][tmdb-1]"
    folder.mkdir()
    for index in indexes:
        (folder / f"Film [2001][tmdb-1] - {index:04d}.jxl").write_text(str(index))
    return folder


def test_next_index_is_max_plus_one(tmp_path):
    images = scan_entity(make_movie(tmp_path)).images
    assert next_index(images) == 8


def test_next_index_refuses_overflow(tmp_path):
    image = ImageFile(path=tmp_path / "x", name="x", index=9999, picked=False, flags=frozenset(), variant=None)
    with pytest.raises(IndexExhausted):
        next_index([image])


def test_resolve_under_rejects_traversal_and_symlink(tmp_path):
    with pytest.raises(PathEscape):
        resolve_under(tmp_path, Path("../etc/passwd"))
    (tmp_path / "link").symlink_to("/etc")
    with pytest.raises(PathEscape):
        resolve_under(tmp_path, Path("link/passwd"))


def test_resolve_under_accepts_inside_path(tmp_path):
    (tmp_path / "folder").mkdir()
    assert resolve_under(tmp_path, Path("folder")) == (tmp_path / "folder").resolve()


def test_toggle_pick_renames_atomically(tmp_path):
    movie = make_movie(tmp_path)
    image = scan_entity(movie).images[0]
    new_path = toggle_pick(image, SCOPE)
    assert new_path.name == "Film [2001][tmdb-1] - 0001+.jxl"
    assert new_path.read_text() == "1"
    assert not (movie / "Film [2001][tmdb-1] - 0001.jxl").exists()


def test_toggle_pick_removes_the_pick(tmp_path):
    movie = make_movie(tmp_path, (1,))
    image = scan_entity(movie).images[0]
    picked = toggle_pick(image, SCOPE)
    image = scan_entity(movie).images[0]
    assert picked.name.endswith("0001+.jxl")
    assert toggle_pick(image, SCOPE).name.endswith("0001.jxl")


def test_rename_refuses_to_overwrite(tmp_path):
    movie = make_movie(tmp_path)
    images = scan_entity(movie).images
    with pytest.raises(FileExistsError):
        rename_image(images[0], SCOPE, ImageName(7))


def test_rename_changes_flags(tmp_path):
    movie = make_movie(tmp_path, (1,))
    image = scan_entity(movie).images[0]
    new_path = rename_image(image, SCOPE, ImageName(1, False, frozenset({"M", "U"}), None))
    assert new_path.name == "Film [2001][tmdb-1] - 0001 [UM].jxl"
