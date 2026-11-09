import re
from pathlib import Path

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from filesystem.operations import PathEscape, resolve_under
from filesystem.scan import Entity, scan_archive
from jobs.models import enqueue

from .forms import ImportForm
from .services import DEFAULT_TYPE_MAP, build_plan, detect_pattern


def _episode_entities(entity: Entity):
    if entity.kind == "episode":
        yield entity
    for child in entity.children:
        yield from _episode_entities(child)


def target_choices(root: Path) -> list[tuple[str, str]]:
    archive = scan_archive(root)
    choices: list[tuple[str, str]] = []
    for entity in (*archive.movies, *archive.others):
        choices.append((entity.path.relative_to(root).as_posix(), entity.title))
    for series in archive.series:
        for episode in _episode_entities(series):
            label = f"{series.title} — {episode.path.relative_to(series.path).as_posix()}"
            choices.append((episode.path.relative_to(root).as_posix(), label))
    return sorted(choices, key=lambda item: item[1].casefold())


def _browse_path(path: str) -> Path:
    try:
        folder = resolve_under(settings.IMPORT_ROOT, path)
    except PathEscape as exc:
        raise Http404 from exc
    if not folder.is_dir():
        raise Http404
    return folder


def importer_index(request):
    root = settings.WALLPAPER_ROOT
    targets = target_choices(root)
    initial = {"source": request.GET.get("source", "")}
    if request.method == "POST" and request.POST.get("action") == "detect":
        data = request.POST.copy()
        form = ImportForm(data, targets=targets)
        detected = None
        try:
            source = resolve_under(settings.IMPORT_ROOT, request.POST.get("source", ""))
            detected = detect_pattern(source)
            if detected is None:
                form.add_error(None, "No index/type pattern was found in the image filenames.")
            else:
                data["regex"] = detected.regex
                form = ImportForm(data, targets=targets)
        except (PathEscape, OSError) as exc:
            form.add_error(None, str(exc))
        return render(
            request,
            "importer/index.html",
            {"form": form, "plan": None, "detected": detected},
        )

    form = ImportForm(request.POST or None, targets=targets, initial=initial)
    plan = None
    if request.method == "POST" and form.is_valid():
        try:
            target = resolve_under(root, form.cleaned_data["target"])
            source = resolve_under(settings.IMPORT_ROOT, form.cleaned_data["source"])
            plan = build_plan(
                source_root=source,
                target=target,
                pattern=re.compile(form.cleaned_data["regex"]),
                type_map=DEFAULT_TYPE_MAP,
            )
        except (PathEscape, ValueError) as exc:
            form.add_error(None, str(exc))
    return render(request, "importer/index.html", {"form": form, "plan": plan, "detected": None})


def importer_browse(request):
    root = settings.IMPORT_ROOT
    if not root.is_dir():
        return render(
            request,
            "importer/browse.html",
            {"current": "", "entries": [], "crumbs": [], "parent": None, "missing": True},
        )
    current = request.GET.get("path", "")
    folder = _browse_path(current)
    entries = []
    for entry in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
        if entry.is_dir() and not entry.is_symlink() and not entry.name.startswith("."):
            entries.append(
                {
                    "name": entry.name,
                    "rel": entry.relative_to(root).as_posix(),
                }
            )
    crumbs = []
    for index, part in enumerate(Path(current).parts):
        crumbs.append({"name": part, "rel": Path(*Path(current).parts[: index + 1]).as_posix()})
    parent = None
    if current:
        parent = Path(current).parent.as_posix()
        if parent == ".":
            parent = ""
    return render(
        request,
        "importer/browse.html",
        {"current": current, "entries": entries, "crumbs": crumbs, "parent": parent, "missing": False},
    )


@require_POST
def importer_run(request):
    form = ImportForm(request.POST, targets=target_choices(settings.WALLPAPER_ROOT))
    if form.is_valid():
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
    return render(request, "importer/index.html", {"form": form, "plan": None, "detected": None})
