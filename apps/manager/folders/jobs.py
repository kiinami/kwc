from django.conf import settings
from jobs.registry import register

from filesystem.operations import rename_entity, resolve_under
from tmdb import TMDBClient

from .services import add_season, build_series_from_tmdb, delete_entity


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


@register("folders.delete")
def delete_job(job, ctx):
    folder = resolve_under(settings.WALLPAPER_ROOT, job.params["path"])
    moved = delete_entity(folder=folder, trash_root=settings.WALLPAPER_ROOT / ".trash")
    return {"path": str(moved.relative_to(settings.WALLPAPER_ROOT))}


@register("folders.rename")
def rename_job(job, ctx):
    folder = resolve_under(settings.WALLPAPER_ROOT, job.params["path"])
    path = rename_entity(
        folder,
        new_title=job.params["new_title"],
        new_year=job.params.get("new_year"),
        new_tmdb_id=job.params.get("new_tmdb_id"),
    )
    return {"path": path.name}
