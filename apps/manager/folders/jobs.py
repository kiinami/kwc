from django.conf import settings
from jobs.registry import register

from filesystem.operations import resolve_under
from tmdb import TMDBClient

from .services import add_season, build_series_from_tmdb


@register("folders.create_series")
def create_series_job(job, ctx):
    client = TMDBClient(settings.TMDB_READ_TOKEN)
    detail = client.series(int(job.params["tmdb_id"]))
    path = build_series_from_tmdb(
        root=settings.WALLPAPER_ROOT,
        detail=detail,
        copyright=job.params.get("copyright", ""),
    )
    return {"path": path.name}


@register("folders.add_season")
def add_season_job(job, ctx):
    series_path = resolve_under(settings.WALLPAPER_ROOT, job.params["series_path"])
    client = TMDBClient(settings.TMDB_READ_TOKEN)
    detail = client.series(int(job.params["tmdb_id"]))
    number = int(job.params["season_number"])
    season = next((item for item in detail.seasons if item.season_number == number), None)
    if season is None:
        raise ValueError(f"season {number} not found on TMDB")
    path = add_season(series_path=series_path, season=season)
    return {"path": path.name}
