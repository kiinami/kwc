import re

from django.conf import settings
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from jobs.models import enqueue

from filesystem.operations import PathEscape, resolve_under

from .forms import ImportForm
from .services import DEFAULT_TYPE_MAP, build_plan


def importer_index(request):
    form = ImportForm(request.POST or None)
    plan = None
    if request.method == "POST" and form.is_valid():
        try:
            target = resolve_under(settings.WALLPAPER_ROOT, form.cleaned_data["target"])
            source = resolve_under(settings.IMPORT_ROOT, form.cleaned_data["source"])
            plan = build_plan(
                source_root=source,
                target=target,
                pattern=re.compile(form.cleaned_data["regex"]),
                type_map=DEFAULT_TYPE_MAP,
            )
        except (PathEscape, ValueError) as exc:
            form.add_error(None, str(exc))
    return render(request, "importer/index.html", {"form": form, "plan": plan})


@require_POST
def importer_run(request):
    form = ImportForm(request.POST)
    if not form.is_valid():
        return render(request, "importer/index.html", {"form": form, "plan": None})
    enqueue(
        "importer.run",
        {
            "target": form.cleaned_data["target"],
            "source": form.cleaned_data["source"],
            "regex": form.cleaned_data["regex"],
            "pick_all": form.cleaned_data["pick_all"],
        },
    )
    return redirect("folder-list")
