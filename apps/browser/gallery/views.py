import logging
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render

from filesystem.metadata import MetadataError, read_metadata
from filesystem.operations import PathEscape, resolve_under
from filesystem.ordering import sort_entities
from filesystem.scan import Entity, scan_archive, scan_entity
from media.derivatives import DerivativeCache
from media.metadata import read_image_metadata


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
    entities = sort_entities([*archive.movies, *archive.series, *archive.others])
    rows = [_row(root, entity) for entity in entities if _visible(entity)]
    return render(
        request,
        "gallery/index.html",
        {"rows": rows, "download_max_bytes": settings.KWC_DOWNLOAD_MAX_BYTES},
    )


def folder(request, path: str):
    if any(part.startswith(".") for part in Path(path).parts):
        raise Http404
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
            "download_max_bytes": settings.KWC_DOWNLOAD_MAX_BYTES,
        },
    )


logger = logging.getLogger(__name__)


def _target(request, path: str) -> Path:
    if any(part.startswith(".") and part != ".cover.jxl" for part in Path(path).parts):
        raise Http404
    root = settings.WALLPAPER_ROOT
    try:
        target = resolve_under(root, path)
    except PathEscape as exc:
        raise Http404 from exc
    if not target.is_file() or target.suffix.lower() != ".jxl":
        raise Http404
    if _hidden_in_path(root, target.parent):
        raise Http404
    return target


def _cache() -> DerivativeCache:
    return DerivativeCache(
        settings.KWC_BROWSER_CACHE_ROOT,
        max_bytes=settings.KWC_BROWSER_CACHE_MAX_BYTES,
    )


def _derivative(request, path: str, kind: str):
    target = _target(request, path)
    relative = target.relative_to(settings.WALLPAPER_ROOT).as_posix()
    cache = _cache()
    try:
        output = cache.thumb(target, relative) if kind == "thumb" else cache.lens(target, relative)
    except Exception as exc:
        logger.exception("derivative failed for %s", relative)
        raise Http404 from exc
    response = FileResponse(output.open("rb"), content_type="image/avif")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    response["ETag"] = f'"{output.stem}"'
    return response


def thumb(request, path: str):
    return _derivative(request, path, "thumb")


def lens_image(request, path: str):
    return _derivative(request, path, "lens")


def lens(request, path: str):
    if any(part.startswith(".") for part in Path(path).parts):
        raise Http404
    root = settings.WALLPAPER_ROOT
    try:
        folder = resolve_under(root, path)
    except PathEscape as exc:
        raise Http404 from exc
    if not folder.is_dir() or _hidden_in_path(root, folder):
        raise Http404
    entity = scan_entity(folder)
    groups = _groups(entity)
    if not groups:
        raise Http404
    try:
        index = int(request.GET.get("index", groups[0]["index"]))
    except ValueError as exc:
        raise Http404 from exc
    selected = next((group for group in groups if group["index"] == index), None)
    if selected is None:
        raise Http404
    position = [group["index"] for group in groups].index(index)
    folder_rel = entity.path.relative_to(root).as_posix()
    variants = [
        {
            "image": image,
            "rel": f"{folder_rel}/{image.name}",
        }
        for image in entity.images
        if image.index == index
    ]
    return render(
        request,
        "gallery/lens.html",
        {
            "entity": entity,
            "selected": selected,
            "selected_rel": f"{folder_rel}/{selected['image'].name}",
            "variants": variants,
            "index": index,
            "prev_index": groups[position - 1]["index"] if position > 0 else None,
            "next_index": groups[position + 1]["index"] if position + 1 < len(groups) else None,
            "folder_rel": folder_rel,
            "image_metadata": read_image_metadata(selected["image"].path),
            "copyright": entity.metadata.copyright if entity.metadata else "",
        },
    )


def original(request, path: str):
    target = _target(request, path)
    response = FileResponse(target.open("rb"), content_type="image/jxl")
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{target.name}"'
    return response


def _all_images(entity: Entity):
    if entity.metadata and entity.metadata.hidden:
        return
    yield from entity.images
    for child in entity.children:
        yield from _all_images(child)


def downloads_json(request):
    root = settings.WALLPAPER_ROOT
    curated = request.GET.get("curated", "1") != "0"
    archive = scan_archive(root)
    images = []
    for entity in (*archive.movies, *archive.series, *archive.others):
        if not _visible(entity):
            continue
        for image in _all_images(entity):
            if curated and not image.picked:
                continue
            relative = image.path.relative_to(root).as_posix()
            images.append({"name": image.name, "url": f"/i/{quote(relative)}"})
    return JsonResponse({"images": images})


def takedown(request):
    return render(request, "gallery/takedown.html", {"email": getattr(settings, "KWC_TAKEDOWN_EMAIL", "")})
