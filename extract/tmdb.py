"""TMDB (The Movie Database) integration for cover art selection."""

from __future__ import annotations

import logging
from typing import TypedDict

try:
    import tmdbsimple as tmdb
    from tmdbsimple.base import APIKeyError
except ImportError:  # pragma: no cover
    tmdb = None
    APIKeyError = Exception

logger = logging.getLogger(__name__)


class SearchResult(TypedDict):
    """A simplified movie/TV show search result."""
    id: int
    title: str
    release_date: str
    media_type: str  # "movie" or "tv"
    poster_path: str | None


class PosterImage(TypedDict):
    """A poster image with its URL and metadata."""
    file_path: str
    url: str
    width: int
    height: int
    vote_average: float


def is_available() -> bool:
    """Check if TMDB integration is available (library installed and API key configured)."""
    return tmdb is not None


def configure_api_key(api_key: str) -> None:
    """Configure the TMDB API key."""
    if tmdb is None:
        raise RuntimeError("tmdbsimple is not installed")
    tmdb.API_KEY = api_key


def search_multi(query: str, *, year: int | None = None) -> list[SearchResult]:
    """Search for movies and TV shows by title.

    Args:
        query: The title to search for
        year: Optional year to filter results

    Returns:
        A list of search results sorted by popularity

    Raises:
        RuntimeError: If TMDB is not available or not configured
    """
    if tmdb is None:
        raise RuntimeError("tmdbsimple is not installed")
    if not tmdb.API_KEY:
        raise RuntimeError("TMDB API key is not configured")

    search = tmdb.Search()
    
    try:
        # Use multi search to find both movies and TV shows
        if year:
            response = search.multi(query=query, year=year)
        else:
            response = search.multi(query=query)
    except APIKeyError:
        logger.error("Invalid TMDB API key")
        raise RuntimeError("Invalid TMDB API key")
    except Exception as e:
        logger.error(f"TMDB search failed: {e}")
        raise RuntimeError(f"TMDB search failed: {e}")

    results: list[SearchResult] = []
    for item in response.get('results', []):
        # Only include movies and TV shows with posters
        if item.get('media_type') not in ('movie', 'tv'):
            continue
        if not item.get('poster_path'):
            continue

        # Extract relevant fields
        title = item.get('title') or item.get('name', '')
        release_date = item.get('release_date') or item.get('first_air_date', '')
        
        results.append({
            'id': item['id'],
            'title': title,
            'release_date': release_date,
            'media_type': item['media_type'],
            'poster_path': item['poster_path'],
        })

    return results


def get_posters(media_type: str, media_id: int) -> list[PosterImage]:
    """Get all available posters for a movie or TV show.

    Args:
        media_type: Either "movie" or "tv"
        media_id: The TMDB ID of the media

    Returns:
        A list of poster images sorted by vote average (highest first)

    Raises:
        RuntimeError: If TMDB is not available or not configured
        ValueError: If media_type is invalid
    """
    if tmdb is None:
        raise RuntimeError("tmdbsimple is not installed")
    if not tmdb.API_KEY:
        raise RuntimeError("TMDB API key is not configured")
    if media_type not in ('movie', 'tv'):
        raise ValueError(f"Invalid media_type: {media_type}")

    try:
        if media_type == 'movie':
            media = tmdb.Movies(media_id)
        else:
            media = tmdb.TV(media_id)
        
        response = media.images()
    except APIKeyError:
        logger.error("Invalid TMDB API key")
        raise RuntimeError("Invalid TMDB API key")
    except Exception as e:
        logger.error(f"TMDB get posters failed: {e}")
        raise RuntimeError(f"TMDB get posters failed: {e}")

    posters: list[PosterImage] = []
    base_url = "https://image.tmdb.org/t/p/original"
    
    for poster in response.get('posters', []):
        file_path = poster.get('file_path')
        if not file_path:
            continue
        
        posters.append({
            'file_path': file_path,
            'url': f"{base_url}{file_path}",
            'width': poster.get('width', 0),
            'height': poster.get('height', 0),
            'vote_average': poster.get('vote_average', 0.0),
        })

    # Sort by vote average (highest first), then by resolution (larger first)
    posters.sort(key=lambda p: (p['vote_average'], p['width'] * p['height']), reverse=True)
    
    return posters


def get_poster_url(file_path: str, size: str = "original") -> str:
    """Get the full URL for a poster image.

    Args:
        file_path: The file path from TMDB (e.g., "/abc123.jpg")
        size: The size to use (e.g., "w500", "original"). Default is "original".

    Returns:
        The full URL to the poster image
    """
    base_url = "https://image.tmdb.org/t/p"
    return f"{base_url}/{size}{file_path}"
