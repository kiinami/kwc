from django.shortcuts import render, redirect
from django.http import (
	Http404,
	HttpRequest,
	HttpResponse,
	HttpResponseNotModified,
	JsonResponse,
)
from django.utils.http import http_date, parse_http_date
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import NamedTuple
import logging
import os

from PIL import Image, ImageOps

from .api import APIError, DecisionPayload, apply_decisions, parse_decision_request
from .models import ImageDecision
from .constants import THUMB_MAX_DIMENSION, THUMB_CACHE_SIZE
from .services import load_folder_context, list_gallery_images
from .utils import (
	wallpapers_root,
	validate_folder_name,
)


logger = logging.getLogger(__name__)
def index(request: HttpRequest) -> HttpResponse:
	"""Redirect to the home page."""
	return redirect('home')


def gallery(request: HttpRequest, folder: str) -> HttpResponse:
	"""Grid gallery for a media folder with lightweight fullscreen viewer."""
	try:
		context = list_gallery_images(folder)
	except (ValueError, FileNotFoundError):
		raise Http404("Folder not found")

	return render(request, 'choose/gallery.html', context.to_dict())


def folder(request: HttpRequest, folder: str) -> HttpResponse:
	"""Detail page for a media folder: show a two-pane chooser UI with sidebar and viewport."""
	# Get optional section filters from query params
	season = request.GET.get('season')
	episode = request.GET.get('episode')
	
	try:
		context = load_folder_context(folder, season=season, episode=episode)
	except (ValueError, FileNotFoundError):
		raise Http404("Folder not found")

	return render(request, 'choose/folder.html', context.to_dict())


class _ThumbResult(NamedTuple):
	data: bytes
	content_type: str


def _sanitize_dimension(value: str | None) -> int:
	try:
		if value is None:
			return 0
		dim = int(value)
	except (TypeError, ValueError):
		return 0
	if dim <= 0:
		return 0
	return max(16, min(dim, THUMB_MAX_DIMENSION))


@lru_cache(maxsize=THUMB_CACHE_SIZE)
def _render_thumbnail_cached(path_str: str, width: int, height: int, mtime_ns: int) -> _ThumbResult:
	path = Path(path_str)
	with Image.open(path) as img:
		img = ImageOps.exif_transpose(img)
		max_w = width if width > 0 else THUMB_MAX_DIMENSION
		max_h = height if height > 0 else THUMB_MAX_DIMENSION
		img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

		has_alpha = img.mode in ("LA", "RGBA") or (img.mode == "P" and "transparency" in img.info)
		buffer = BytesIO()
		if has_alpha:
			if img.mode not in ("LA", "RGBA"):
				img = img.convert("RGBA")
			img.save(buffer, "PNG", optimize=True)
			content_type = "image/png"
		else:
			if img.mode not in ("RGB", "L"):
				img = img.convert("RGB")
			elif img.mode == "L":
				img = img.convert("RGB")
			img.save(buffer, "JPEG", quality=82, optimize=True, progressive=True)
			content_type = "image/jpeg"

	return _ThumbResult(buffer.getvalue(), content_type)


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

	root = wallpapers_root()
	source = root / folder / safe_filename
	if not source.exists() or not source.is_file():
		raise Http404("Image not found")

	stat = source.stat()
	width = _sanitize_dimension(request.GET.get('w'))
	height = _sanitize_dimension(request.GET.get('h'))
	if width <= 0 and height <= 0:
		width = 512

	try:
		result = _render_thumbnail_cached(str(source), width, height, stat.st_mtime_ns)
	except OSError:
		raise Http404("Unable to generate thumbnail")

	etag = f'W/"thumb-{stat.st_mtime_ns:x}-{width}-{height}"'
	if request.headers.get('If-None-Match') == etag:
		return HttpResponseNotModified()
	ims = request.headers.get('If-Modified-Since')
	if ims:
		try:
			if parse_http_date(ims) >= int(stat.st_mtime):
				return HttpResponseNotModified()
		except (ValueError, OverflowError):
			pass

	content_length = len(result.data)
	response = HttpResponse(result.data, content_type=result.content_type)
	if request.method == 'HEAD':
		response.content = b''

	response['Cache-Control'] = 'public, max-age=31536000, immutable'
	response['Content-Length'] = str(content_length)
	response['ETag'] = etag
	response['Last-Modified'] = http_date(stat.st_mtime)
	return response


@require_POST
def decide_api(request: HttpRequest, folder: str) -> JsonResponse:
	"""Persist a keep/delete decision for an image in a given folder.

	JSON body: { "filename": str, "decision": "keep"|"delete" }
	"""
	try:
		safe_name = validate_folder_name(folder)
	except ValueError:
		return JsonResponse({"error": "invalid_folder"}, status=400)
	try:
		payload = parse_decision_request(request.body)
	except APIError as exc:
		return JsonResponse({"error": exc.code}, status=exc.status)
	except Exception as exc:  # pragma: no cover - defensive
		logger.exception("Unexpected error parsing decision payload for %s", folder)
		return JsonResponse({"error": "invalid_json"}, status=400)

	filename = payload.filename
	decision = payload.decision
	if not filename:
		return JsonResponse({"error": "missing_filename"}, status=400)
	if decision not in (ImageDecision.DECISION_KEEP, ImageDecision.DECISION_DELETE, ""):
		return JsonResponse({"error": "invalid_decision"}, status=400)
	if decision == "":
		ImageDecision.objects.filter(folder=safe_name, filename=filename).delete()
		return JsonResponse({"ok": True, "folder": safe_name, "filename": filename, "decision": ""})
	obj, _created = ImageDecision.objects.update_or_create(
		folder=safe_name,
		filename=filename,
		defaults={"decision": decision},
	)
	return JsonResponse({"ok": True, "folder": obj.folder, "filename": obj.filename, "decision": obj.decision})


@require_POST
def save_api(request: HttpRequest, folder: str) -> JsonResponse:
	"""Apply decisions: delete 'delete' images, and rename kept images to close gaps using EXTRACT_IMAGE_PATTERN counter.

	Undecided images are treated as 'keep'. Files are not moved between folders, only renamed in-place.
	"""
	content_type = request.headers.get("Content-Type", "")
	payload = DecisionPayload()
	if request.body and "json" in content_type.lower():
		try:
			payload = parse_decision_request(request.body)
		except APIError as exc:
			return JsonResponse({"error": exc.code}, status=exc.status)
		except Exception as exc:  # pragma: no cover - defensive
			logger.exception("Unexpected error parsing request body for save_api on %s", folder)
			return JsonResponse({"error": "invalid_json"}, status=400)
	elif request.body:
		logger.debug(
			"Ignoring non-JSON payload for save_api on %s with content type %s",
			folder,
			content_type or "<missing>",
		)

	try:
		with transaction.atomic():
			result = apply_decisions(folder, payload)
	except APIError as exc:
		return JsonResponse({"error": exc.code}, status=exc.status)
	except Exception as exc:  # pragma: no cover - defensive
		logger.exception("Unexpected error applying decisions for %s", folder)
		return JsonResponse({"error": "unexpected_error"}, status=500)

	return JsonResponse(result.payload, status=result.status)
