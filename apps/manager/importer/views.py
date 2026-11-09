import re

from django.conf import settings
from django.shortcuts import render

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
