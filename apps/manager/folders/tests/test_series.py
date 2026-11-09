import pytest
from folders.services import add_season, build_series_from_tmdb, promote_flat_series

from filesystem.metadata import read_metadata
from tmdb import EpisodeDetail, SeasonDetail, SeriesDetail


def season(number: int, episodes: int = 2) -> SeasonDetail:
    return SeasonDetail(
        season_number=number,
        name=f"Season {number}",
        air_date=f"202{number}-01-01",
        episodes=tuple(
            EpisodeDetail(index, f"Episode {number}-{index}", f"202{number}-01-0{index}")
            for index in range(1, episodes + 1)
        ),
    )


def series(*seasons: SeasonDetail) -> SeriesDetail:
    return SeriesDetail(
        id=9,
        name="Show",
        original_name="Show Original",
        first_air_date="2021-01-01",
        last_air_date="2022-06-01",
        seasons=tuple(seasons),
    )


def test_single_season_series_skips_season_folder(tmp_path):
    path = build_series_from_tmdb(root=tmp_path, detail=series(season(1)))
    assert (path / "E01").is_dir()
    assert (path / "E02").is_dir()
    assert not (path / "S01").exists()
    assert read_metadata(path / "E01").title == "Episode 1-1"
    assert read_metadata(path).first_release_date == "2021-01-01"


def test_two_season_series_uses_season_folders(tmp_path):
    path = build_series_from_tmdb(root=tmp_path, detail=series(season(1), season(2)))
    assert (path / "S01" / "E01").is_dir()
    assert (path / "S02" / "E01").is_dir()
    assert read_metadata(path / "S02").season == 2
    assert not (path / "E01").exists()


def test_adding_second_season_promotes_flat_layout(tmp_path):
    path = build_series_from_tmdb(root=tmp_path, detail=series(season(1)))
    add_season(series_path=path, season=season(2))
    assert (path / "S01" / "E01").is_dir()
    assert (path / "S02" / "E01").is_dir()
    assert not (path / "E01").exists()


def test_promote_is_idempotent_for_season_layout(tmp_path):
    path = build_series_from_tmdb(root=tmp_path, detail=series(season(1), season(2)))
    promote_flat_series(path)
    assert (path / "S01" / "E01").is_dir()


def test_duplicate_season_raises(tmp_path):
    path = build_series_from_tmdb(root=tmp_path, detail=series(season(1), season(2)))
    with pytest.raises(FileExistsError):
        add_season(series_path=path, season=season(2))


def test_series_without_air_date_raises(tmp_path):
    detail = SeriesDetail(9, "Show", "Show", None, None, (season(1),))
    with pytest.raises(ValueError):
        build_series_from_tmdb(root=tmp_path, detail=detail)
