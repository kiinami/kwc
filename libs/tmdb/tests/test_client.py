import pytest
import responses

from tmdb import MovieDetail, Poster, TMDBClient, TMDBError
from tmdb import client as client_module

BASE = "https://api.themoviedb.org/3"


def make_client() -> TMDBClient:
    return TMDBClient("token")


@responses.activate
def test_search_movies_maps_results():
    responses.get(
        f"{BASE}/search/movie",
        json={
            "results": [
                {"id": 1, "title": "Film", "original_title": "Film", "release_date": "2001-01-01"},
            ]
        },
    )
    result = make_client().search_movies("Film", year=2001)
    assert result == [MovieDetail(1, "Film", "Film", "2001-01-01")]
    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer token"
    assert "query=Film" in request.url
    assert "year=2001" in request.url


@responses.activate
def test_search_series_maps_results():
    responses.get(
        f"{BASE}/search/tv",
        json={"results": [{"id": 2, "name": "Show", "original_name": "Show", "first_air_date": "2020-01-01"}]},
    )
    result = make_client().search_series("Show")
    assert result[0].id == 2
    assert result[0].seasons == ()


@responses.activate
def test_series_fetches_every_season():
    responses.get(
        f"{BASE}/tv/9",
        json={
            "id": 9,
            "name": "Show",
            "original_name": "Show",
            "first_air_date": "2020-01-01",
            "last_air_date": "2021-01-01",
            "seasons": [{"season_number": 1, "name": "Season 1", "air_date": "2020-01-01"}],
        },
    )
    responses.get(
        f"{BASE}/tv/9/season/1",
        json={
            "season_number": 1,
            "name": "Season 1",
            "air_date": "2020-01-01",
            "episodes": [{"episode_number": 1, "name": "Pilot", "air_date": "2020-01-01"}],
        },
    )
    result = make_client().series(9)
    assert result.last_air_date == "2021-01-01"
    assert result.seasons[0].episodes[0].name == "Pilot"


@responses.activate
def test_retries_once_on_429(monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda _: None)
    responses.get(f"{BASE}/movie/1", status=429)
    responses.get(f"{BASE}/movie/1", json={"id": 1, "title": "Film", "original_title": "Film"})
    assert make_client().movie(1).title == "Film"


@responses.activate
def test_posters_include_every_language_and_are_ordered_by_votes():
    responses.get(
        f"{BASE}/movie/1/images",
        json={
            "posters": [
                {"file_path": "/a.jpg", "iso_639_1": "en", "vote_average": 5, "vote_count": 10},
                {"file_path": "/b.jpg", "iso_639_1": None, "vote_average": 8, "vote_count": 20},
                {"file_path": "/c.jpg", "iso_639_1": "fr", "vote_average": 9, "vote_count": 30},
            ]
        },
    )
    posters = make_client().posters(1)
    assert [poster.file_path for poster in posters] == ["/c.jpg", "/b.jpg", "/a.jpg"]
    assert posters[0] == Poster("/c.jpg", "fr", 9.0, 30)


@responses.activate
def test_download_image_returns_bytes():
    responses.get("https://image.tmdb.org/t/p/original/p.jpg", body=b"image-bytes")
    assert make_client().download_image("/p.jpg") == b"image-bytes"


def test_download_image_rejects_traversal():
    with pytest.raises(ValueError):
        make_client().download_image("../etc/passwd")


@responses.activate
def test_non_retryable_error_raises():
    responses.get(f"{BASE}/movie/1", status=404, json={"status_message": "not found"})
    try:
        make_client().movie(1)
    except TMDBError:
        pass
    else:
        raise AssertionError("expected TMDBError")
