"""Choose app views."""
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseNotModified,
    JsonResponse,
)
from django.shortcuts import render
from django.utils.http import http_date, parse_http_date
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from django.urls import reverse
import logging
import os

from .api import APIError, DecisionPayload, apply_decisions, parse_decision_request
from .models import ImageDecision
from .chooser_services import load_folder_context
from .folder_utils import list_extract_folders
from common.thumbnails import sanitize_dimension, render_thumbnail_cached
from common.utils import extract_root, validate_folder_name, wallpapers_root

logger = logging.getLogger(__name__)


def index(request: HttpRequest) -> HttpResponse:
    """Choose home: list folders from extraction area for review."""
    folders, root = list_extract_folders()
    
    enriched: list[dict] = []
    for entry in folders:
        # Build display text for season/episode
        season_episode_text = ""
        if entry['season'] and entry['episode']:
            season_episode_text = f"S{entry['season']}E{entry['episode']}"
        elif entry['season']:
            season_episode_text = f"Season {entry['season']}"
        elif entry['episode']:
            episode_upper = entry['episode'].upper()
            if episode_upper == "IN":
                season_episode_text = "Intro"
            elif episode_upper == "OU":
                season_episode_text = "Outro"
            else:
                season_episode_text = f"Episode {entry['episode']}"
        
        enriched.append(
            {
                **entry,
                'season_episode_text': season_episode_text,
                'choose_url': reverse('choose:folder', kwargs={'folder': entry['name']}),
            }
        )
    
    return render(request, 'choose/index.html', {
        'folders': enriched,
        'root': str(root),
    })


def folder(request: HttpRequest, folder: str) -> HttpResponse:
    """Chooser interface for a specific folder."""
    season = request.GET.get('season')
    episode = request.GET.get('episode')
    
    try:
        context = load_folder_context(folder, season=season, episode=episode)
    except (ValueError, FileNotFoundError) as e:
        raise Http404(str(e)) from e
    
    template_context = context.to_dict()
    template_context['folder'] = context.folder
    
    return render(request, 'choose/folder.html', template_context)


@require_GET
def thumbnail(request: HttpRequest, folder: str, filename: str) -> HttpResponse:
    """Serve a resized thumbnail for a wallpaper without storing it on disk."""
    try:
        validate_folder_name(folder)
    except ValueError:
        raise Http404("Invalid folder")
    
    safe_filename = os.path.basename(filename)
    if safe_filename != filename:
        raise Http404("Invalid filename")

    # Try wallpapers root first, then extract root
    wallpapers_path = wallpapers_root()
    source = wallpapers_path / folder / safe_filename
    
    if not source.exists() or not source.is_file():
        # Try extract root
        extract_path = extract_root()
        source = extract_path / folder / safe_filename
        
        if not source.exists() or not source.is_file():
            raise Http404("Image not found")

    try:
        stat = source.stat()
        mtime_ns = stat.st_mtime_ns
    except OSError:
        raise Http404("Image not accessible")

    last_modified = http_date(stat.st_mtime)
    if_modified_since = request.META.get("HTTP_IF_MODIFIED_SINCE")
    if if_modified_since:
        try:
            if parse_http_date(if_modified_since) >= stat.st_mtime:
                return HttpResponseNotModified()
        except (ValueError, OverflowError):
            pass

    width = sanitize_dimension(request.GET.get("w"))
    height = sanitize_dimension(request.GET.get("h"))

    result = render_thumbnail_cached(str(source), width, height, mtime_ns)

    response = HttpResponse(result.data, content_type=result.content_type)
    response["Last-Modified"] = last_modified
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@require_POST
def decide_api(request: HttpRequest, folder: str) -> JsonResponse:
    """Record a keep/discard decision for an image."""
    try:
        validate_folder_name(folder)
    except ValueError:
        return JsonResponse({"error": "invalid_folder"}, status=400)

    try:
        payload = parse_decision_request(request.body)
    except Exception as e:
        logger.warning("Malformed decide request for %s: %s", folder, e)
        return JsonResponse({"error": "invalid_json"}, status=400)

    if not payload.filename:
        return JsonResponse({"error": "missing_filename"}, status=400)

    if payload.decision not in {ImageDecision.DECISION_KEEP, ImageDecision.DECISION_DELETE}:
        return JsonResponse({"error": "invalid_decision"}, status=400)

    with transaction.atomic():
        obj, created = ImageDecision.objects.update_or_create(
            folder=folder,
            filename=payload.filename,
            defaults={"decision": payload.decision},
        )

    return JsonResponse({"ok": True, "created": created})


@require_POST
def save_api(request: HttpRequest, folder: str) -> JsonResponse:
    """Apply decisions: move kept images to wallpapers folder, delete discarded ones."""
    try:
        payload = parse_decision_request(request.body)
    except Exception as e:
        logger.warning("Malformed save request for %s: %s", folder, e)
        return JsonResponse({"error": "invalid_json"}, status=400)

    try:
        result = apply_decisions(folder, payload)
        return JsonResponse(result.payload, status=result.status)
    except APIError as e:
        logger.warning("API error applying decisions for %s: %s", folder, e.detail or e.code)
        return JsonResponse(
            {"error": e.code, "detail": e.detail},
            status=e.status,
        )
    except Exception as e:
        logger.exception("Unexpected error applying decisions for %s", folder)
        return JsonResponse(
            {"error": "internal_error", "detail": str(e)},
            status=500,
        )
