import pytest
from filesystem.naming import (
    FolderRef,
    ImageName,
    NameScope,
    episode_folder,
    folder_name,
    format_type,
    image_filename,
    parse_episode_folder,
    parse_folder_name,
    parse_image_filename,
    parse_season_folder,
    parse_type,
    season_folder,
)


def test_folder_names():
    assert folder_name("Spirited Away", year=2001, tmdb_id=129) == "Spirited Away [2001][tmdb-129]"
    assert parse_folder_name("Spirited Away [2001][tmdb-129]") == FolderRef("Spirited Away", 2001, 129)
    assert parse_folder_name("Other Name") == FolderRef("Other Name")
    assert parse_folder_name("Bad [2001]") is None


def test_image_names_with_flags_and_picks():
    scope = NameScope("Spirited Away", 2001, 129)
    assert image_filename(scope, ImageName(7)) == "Spirited Away [2001][tmdb-129] - 0007.jxl"
    assert image_filename(scope, ImageName(7, True, frozenset({"M", "U"}))) == (
        "Spirited Away [2001][tmdb-129] - 0007+ [UM].jxl"
    )
    assert parse_image_filename("Spirited Away [2001][tmdb-129] - 0007+ [UM].jxl", scope) == (
        ImageName(7, True, frozenset({"M", "U"}))
    )


def test_series_image_names():
    scope = NameScope("Mob Psycho 100", 2016, 67075, season=1, episode="E03")
    name = image_filename(scope, ImageName(4))
    assert name == "Mob Psycho 100 [2016][tmdb-67075] - S01E03 - 0004.jxl"
    assert parse_image_filename(name, scope) == ImageName(4)


def test_rejects_bad_indexes_and_flags():
    scope = NameScope("Other")
    assert parse_image_filename("Other - 10000.jxl", scope) is None
    assert parse_image_filename("Other - 0001 [X].jxl", scope) is None
    assert parse_type("[MU]") == (frozenset({"U", "M"}), None)
    assert format_type(frozenset({"M", "U"}), None) == "[UM]"


def test_type_variants_are_numbered():
    assert parse_type("[A1]") == (frozenset({"A"}), 1)
    assert parse_type("[UM2]") == (frozenset({"U", "M"}), 2)
    assert format_type(frozenset({"U", "M"}), 2) == "[UM2]"
    assert parse_type("[]") is None
    assert parse_type("[MM]") is None
    assert format_type(frozenset(), 1) == ""


def test_title_validation():
    with pytest.raises(ValueError):
        folder_name("Bad/Title", year=2001, tmdb_id=1)
    with pytest.raises(ValueError):
        folder_name("Bad [Title]", year=2001, tmdb_id=1)
    with pytest.raises(ValueError):
        folder_name("No Year", tmdb_id=1)


def test_season_and_episode_folders():
    assert season_folder(1) == "S01"
    assert parse_season_folder("S00") == 0
    assert parse_season_folder("S1") is None
    assert episode_folder("e03") == "E03"
    assert episode_folder("EIN1") == "EIN1"
    assert parse_episode_folder("EOUT") == "EOUT"
    assert parse_episode_folder("E100") is None
