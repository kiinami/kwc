import re

from django.conf import settings

from filesystem.metadata import read_metadata
from filesystem.operations import resolve_under
from jobs.registry import register

from .services import DEFAULT_TYPE_MAP, build_plan, run_plan


@register("importer.run")
def import_job(job, ctx):
    target = resolve_under(settings.WALLPAPER_ROOT, job.params["target"])
    source = resolve_under(settings.IMPORT_ROOT, job.params["source"])
    plan = build_plan(
        source_root=source,
        target=target,
        pattern=re.compile(job.params["regex"]),
        type_map=DEFAULT_TYPE_MAP,
    )
    metadata = read_metadata(target)
    return run_plan(
        plan=plan,
        target=target,
        pick_all=bool(job.params.get("pick_all")),
        copyright=metadata.copyright if metadata and metadata.copyright else "",
        ctx=ctx,
        pixel_budget=settings.IMPORT_PIXEL_BUDGET,
    )
