"""Minimal read-only TMDB v3 client."""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class Poster:
    file_path: str
    language: str | None
    vote_average: float
    vote_count: int


@dataclass(frozen=True)
class MovieDetail:
    id: int
    title: str
    original_title: str
    release_date: str | None
    poster_path: str | None = None


@dataclass(frozen=True)
class EpisodeDetail:
    episode_number: int
    name: str
    air_date: str | None


@dataclass(frozen=True)
class SeasonDetail:
    season_number: int
    name: str
    air_date: str | None
    episodes: tuple[EpisodeDetail, ...]


@dataclass(frozen=True)
class SeriesDetail:
    id: int
    name: str
    original_name: str
    first_air_date: str | None
    last_air_date: str | None
    seasons: tuple[SeasonDetail, ...]
    poster_path: str | None = None


class TMDBError(RuntimeError):
    """TMDB returned an error or an unusable payload."""


class TMDBClient:
    base_url = "https://api.themoviedb.org/3"

    def __init__(self, token: str, *, session: requests.Session | None = None) -> None:
        if not token:
            raise ValueError("TMDB token is required")
        self.token = token
        self.session = session or requests.Session()

    def _get(self, path: str, **params: object) -> dict:
        params.setdefault("language", "en-US")
        headers = {"Authorization": f"Bearer {self.token}", "accept": "application/json"}
        for attempt in range(2):
            response = self.session.get(
                f"{self.base_url}{path}",
                params=params,
                headers=headers,
                timeout=15,
            )
            if (response.status_code == 429 or response.status_code >= 500) and attempt == 0:
                time.sleep(0.5)
                continue
            if response.status_code >= 400:
                raise TMDBError(f"TMDB {response.status_code}: {response.text[:200]}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise TMDBError("TMDB returned invalid JSON") from exc
            if not isinstance(payload, dict):
                raise TMDBError("TMDB returned an unexpected payload")
            return payload
        raise TMDBError("TMDB request failed after retry")

    def search_movies(self, query: str, year: int | None = None) -> list[MovieDetail]:
        params: dict[str, object] = {"query": query}
        if year is not None:
            params["year"] = year
        payload = self._get("/search/movie", **params)
        return [self._movie(item) for item in payload.get("results", [])]

    def search_series(self, query: str) -> list[SeriesDetail]:
        payload = self._get("/search/tv", query=query)
        return [
            SeriesDetail(
                id=int(item["id"]),
                name=str(item.get("name", "")),
                original_name=str(item.get("original_name", "")),
                first_air_date=item.get("first_air_date"),
                last_air_date=item.get("last_air_date"),
                seasons=(),
                poster_path=item.get("poster_path"),
            )
            for item in payload.get("results", [])
        ]

    def movie(self, tmdb_id: int) -> MovieDetail:
        return self._movie(self._get(f"/movie/{tmdb_id}"))

    def series(self, tmdb_id: int) -> SeriesDetail:
        payload = self._get(f"/tv/{tmdb_id}")
        seasons = tuple(
            sorted(
                (self._season(tmdb_id, int(item["season_number"])) for item in payload.get("seasons", [])),
                key=lambda season: season.season_number,
            )
        )
        return SeriesDetail(
            id=int(payload["id"]),
            name=str(payload.get("name", "")),
            original_name=str(payload.get("original_name", "")),
            first_air_date=payload.get("first_air_date"),
            last_air_date=payload.get("last_air_date"),
            seasons=seasons,
            poster_path=payload.get("poster_path"),
        )

    @staticmethod
    def image_url(path: str, size: str = "w500") -> str:
        return f"https://image.tmdb.org/t/p/{size}{path}"

    def posters(self, tmdb_id: int, kind: str = "movie") -> list[Poster]:
        endpoint = "movie" if kind == "movie" else "tv"
        payload = self._get(f"/{endpoint}/{tmdb_id}/images")
        items = [
            Poster(
                file_path=item["file_path"],
                language=item.get("iso_639_1"),
                vote_average=float(item.get("vote_average") or 0),
                vote_count=int(item.get("vote_count") or 0),
            )
            for item in payload.get("posters", [])
            if item.get("file_path")
        ]
        items.sort(key=lambda item: (item.vote_average, item.vote_count), reverse=True)
        return items

    def download_image(self, path: str, size: str = "original") -> bytes:
        if not path.startswith("/") or ".." in path:
            raise ValueError(f"invalid TMDB image path: {path}")
        response = self.session.get(self.image_url(path, size), timeout=30)
        if response.status_code >= 400:
            raise TMDBError(f"TMDB image {response.status_code}: {response.text[:200]}")
        return response.content

    def _movie(self, payload: dict) -> MovieDetail:
        return MovieDetail(
            id=int(payload["id"]),
            title=str(payload.get("title", "")),
            original_title=str(payload.get("original_title", "")),
            release_date=payload.get("release_date"),
            poster_path=payload.get("poster_path"),
        )

    def _season(self, tmdb_id: int, season_number: int) -> SeasonDetail:
        payload = self._get(f"/tv/{tmdb_id}/season/{season_number}")
        episodes = tuple(
            sorted(
                (
                    EpisodeDetail(
                        episode_number=int(item["episode_number"]),
                        name=str(item.get("name", "")),
                        air_date=item.get("air_date"),
                    )
                    for item in payload.get("episodes", [])
                ),
                key=lambda episode: episode.episode_number,
            )
        )
        return SeasonDetail(
            season_number=int(payload.get("season_number", season_number)),
            name=str(payload.get("name", "")),
            air_date=payload.get("air_date"),
            episodes=episodes,
        )
