from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import render

from filesystem.metadata import MetadataError, read_metadata
from filesystem.operations import PathEscape, resolve_under
from filesystem.scan import Entity, scan_archive, scan_entity


def _visible(entity: Entity) -> bool:
    if entity.metadata and entity.metadata.hidden:
        return False
    if entity.images:
        return True
    return any(_visible(child) for child in entity.children)


def _cover(entity: Entity) -> Path | None:
    if entity.cover is not None:
        return entity.cover
    if entity.images:
        return entity.images[0].path
    for child in entity.children:
        found = _cover(child)
        if found is not None:
            return found
    return None


def _row(root: Path, entity: Entity) -> dict:
    cover = _cover(entity)
    return {
        "entity": entity,
        "rel": entity.path.relative_to(root).as_posix(),
        "cover": cover.relative_to(root).as_posix() if cover is not None else None,
    }


def _hidden_in_path(root: Path, folder: Path) -> bool:
    current = folder
    while current != root and current.is_relative_to(root):
        try:
            metadata = read_metadata(current)
        except MetadataError:
            metadata = None
        if metadata is not None and metadata.hidden:
            return True
        current = current.parent
    return False


def _groups(entity: Entity) -> list[dict]:
    grouped: dict[int, list] = {}
    for image in entity.images:
        grouped.setdefault(image.index, []).append(image)
    groups = []
    for index in sorted(grouped):
        images = grouped[index]
        base = next((image for image in images if not image.flags), images[0])
        groups.append(
            {
                "index": index,
                "image": base,
                "count": len(images),
                "picked": any(image.picked for image in images),
            }
        )
    return groups


def index(request):
    root = settings.WALLPAPER_ROOT
    archive = scan_archive(root)
    sections = []
    for label, entities in (
        ("Movies", archive.movies),
        ("Series", archive.series),
        ("Others", archive.others),
    ):
        rows = [_row(root, entity) for entity in entities if _visible(entity)]
        if rows:
            sections.append((label, rows))
    return render(request, "gallery/index.html", {"sections": sections})


def folder(request, path: str):
    root = settings.WALLPAPER_ROOT
    try:
        target = resolve_under(root, path)
    except PathEscape as exc:
        raise Http404 from exc
    if not target.is_dir() or _hidden_in_path(root, target):
        raise Http404
    try:
        entity = scan_entity(target)
    except ValueError as exc:
        raise Http404 from exc
    groups = _groups(entity)
    curated = request.GET.get("curated", "1") != "0"
    shown = [group for group in groups if group["picked"]] if curated else groups
    for group in shown:
        group["rel"] = f"{entity.path.relative_to(root).as_posix()}/{group['image'].name}"
    return render(
        request,
        "gallery/folder.html",
        {
            "entity": entity,
            "rel": entity.path.relative_to(root).as_posix(),
            "groups": shown,
            "total": len(groups),
            "curated_count": sum(1 for group in groups if group["picked"]),
            "curated": curated,
            "children": [_row(root, child) for child in entity.children if _visible(child)],
        },
    )


def original(request, path: str):
    root = settings.WALLPAPER_ROOT
    try:
        target = resolve_under(root, path)
    except PathEscape as exc:
        raise Http404 from exc
    if not target.is_file() or target.suffix.lower() != ".jxl":
        raise Http404
    response = FileResponse(target.open("rb"), content_type="image/jxl")
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{target.name}"'
    return response


def takedown(request):
    return render(request, "gallery/takedown.html", {"email": getattr(settings, "KWC_TAKEDOWN_EMAIL", "")})
