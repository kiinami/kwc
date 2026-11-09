from pathlib import Path

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from jobs.models import enqueue

from filesystem.operations import PathEscape, resolve_under
from filesystem.scan import Entity, scan_archive, scan_entity
from tmdb import TMDBClient, TMDBError

from . import services
from .forms import DeleteForm, FolderCreateForm, RenameForm, SearchForm


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _entity_row(root: Path, entity: Entity) -> dict:
    return {"entity": entity, "rel": _relative(root, entity.path)}


def folder_list(request):
    archive = scan_archive(settings.WALLPAPER_ROOT)
    root = settings.WALLPAPER_ROOT
    return render(
        request,
        "folders/list.html",
        {
            "sections": [
                ("Movies", [_entity_row(root, entity) for entity in archive.movies]),
                ("Series", [_entity_row(root, entity) for entity in archive.series]),
                ("Others", [_entity_row(root, entity) for entity in archive.others]),
            ]
        },
    )


def _folder_or_404(path: str):
    root = settings.WALLPAPER_ROOT
    try:
        folder = resolve_under(root, path)
    except PathEscape as exc:
        raise Http404 from exc
    if not folder.is_dir():
        raise Http404
    return folder


def _detail_context(root: Path, entity: Entity, *, rename_form=None, delete_form=None, error: str = "") -> dict:
    return {
        "entity": entity,
        "rel": _relative(root, entity.path),
        "children": [_entity_row(root, child) for child in entity.children],
        "rename_form": rename_form
        or RenameForm(initial={"new_title": entity.title, "new_year": entity.year, "new_tmdb_id": entity.tmdb_id}),
        "delete_form": delete_form or DeleteForm(),
        "cover_images": [image.name for image in entity.images],
        "error": error,
    }


def folder_detail(request, path: str):
    root = settings.WALLPAPER_ROOT
    folder = _folder_or_404(path)
    try:
        entity = scan_entity(folder)
    except ValueError as exc:
        raise Http404 from exc
    return render(request, "folders/detail.html", _detail_context(root, entity))


def folder_create(request):
    initial = {key: request.GET[key] for key in ("kind", "title", "year", "tmdb_id") if request.GET.get(key)}
    form = FolderCreateForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        root = settings.WALLPAPER_ROOT
        kind = form.cleaned_data["kind"]
        copyright = form.cleaned_data.get("copyright", "")
        try:
            if kind == "movie":
                folder = services.create_movie(
                    root=root,
                    title=form.cleaned_data["title"],
                    year=form.cleaned_data["year"],
                    tmdb_id=form.cleaned_data["tmdb_id"],
                    copyright=copyright,
                )
            elif kind == "series":
                folder = services.create_series(
                    root=root,
                    title=form.cleaned_data["title"],
                    year=form.cleaned_data["year"],
                    tmdb_id=form.cleaned_data["tmdb_id"],
                    copyright=copyright,
                )
            else:
                folder = services.create_other(root=root, title=form.cleaned_data["title"], copyright=copyright)
        except (FileExistsError, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("folder-detail", path=_relative(root, folder))
    return render(
        request,
        "folders/create.html",
        {"form": form, "search_form": SearchForm(initial={"kind": request.GET.get("kind", "movie")})},
    )


@require_POST
def folder_hide(request, path: str):
    folder = _folder_or_404(path)
    services.set_hidden(folder=folder, hidden="hidden" in request.POST)
    return redirect("folder-detail", path=path)


@require_POST
def folder_cover(request, path: str):
    folder = _folder_or_404(path)
    try:
        image = resolve_under(folder, request.POST.get("image", ""))
    except PathEscape as exc:
        raise Http404 from exc
    try:
        services.set_cover(folder=folder, image=image)
    except FileNotFoundError as exc:
        raise Http404 from exc
    return redirect("folder-detail", path=path)


@require_POST
def folder_rename(request, path: str):
    root = settings.WALLPAPER_ROOT
    folder = _folder_or_404(path)
    entity = scan_entity(folder)
    form = RenameForm(request.POST)
    if form.is_valid() and form.cleaned_data["confirm"] == entity.title:
        enqueue(
            "folders.rename",
            {
                "path": _relative(root, folder),
                "new_title": form.cleaned_data["new_title"],
                "new_year": form.cleaned_data.get("new_year"),
                "new_tmdb_id": form.cleaned_data.get("new_tmdb_id"),
            },
        )
        return redirect("folder-list")
    error = "Confirmation did not match the current title." if form.is_valid() else "Check the rename fields."
    return render(request, "folders/detail.html", _detail_context(root, entity, rename_form=form, error=error))


@require_POST
def folder_delete(request, path: str):
    root = settings.WALLPAPER_ROOT
    folder = _folder_or_404(path)
    entity = scan_entity(folder)
    form = DeleteForm(request.POST)
    if form.is_valid() and form.cleaned_data["confirm"] == entity.title:
        enqueue("folders.delete", {"path": _relative(root, folder)})
        return redirect("folder-list")
    error = "Confirmation did not match the title." if form.is_valid() else "Confirmation is required."
    return render(request, "folders/detail.html", _detail_context(root, entity, delete_form=form, error=error))


def folder_search(request):
    form = SearchForm(request.GET or None)
    results: list[dict] = []
    message = ""
    if form.is_valid():
        token = getattr(settings, "TMDB_READ_TOKEN", "")
        if not token:
            message = "TMDB_READ_TOKEN is not configured."
        else:
            client = TMDBClient(token)
            kind = form.cleaned_data["kind"]
            try:
                if kind == "series":
                    hits = client.search_series(form.cleaned_data["query"])
                    results = [
                        {"id": hit.id, "title": hit.name, "year": (hit.first_air_date or "")[:4], "kind": "series"}
                        for hit in hits
                    ]
                else:
                    hits = client.search_movies(form.cleaned_data["query"], year=form.cleaned_data.get("year"))
                    results = [
                        {
                            "id": hit.id,
                            "title": hit.title,
                            "year": (hit.release_date or "")[:4],
                            "kind": "movie",
                        }
                        for hit in hits
                    ]
            except TMDBError as exc:
                message = str(exc)
    return render(
        request,
        "folders/create.html",
        {
            "form": FolderCreateForm(),
            "search_form": form,
            "results": results,
            "message": message,
        },
    )
