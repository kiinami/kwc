from django.shortcuts import render, redirect
from django.http import (
	Http404,
	HttpRequest,
	HttpResponse,
	HttpResponseNotModified,
	JsonResponse,
)
from django.urls import reverse
from django.conf import settings
from django.utils.http import http_date, parse_http_date
from django.views.decorators.http import require_GET, require_POST
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import NamedTuple
import os
import re
import json
from .models import ImageDecision, FolderProgress
from .constants import SEASON_EPISODE_PATTERN, THUMB_MAX_DIMENSION, THUMB_CACHE_SIZE
from extract.utils import render_pattern
from .utils import (
	wallpapers_root,
	parse_folder_name,
	list_image_files,
	find_cover_filename,
	wallpaper_url,
	thumbnail_url,
	list_media_folders,
	validate_folder_name,
	get_folder_path,
	parse_title_year_from_folder,
)
from PIL import Image, ImageOps


# Parse S01E02-like tokens from filenames
SEASON_EPISODE_RE = re.compile(SEASON_EPISODE_PATTERN, re.IGNORECASE)
def index(request: HttpRequest) -> HttpResponse:
	"""Redirect to the home page."""
	return redirect('home')


def gallery(request: HttpRequest, folder: str) -> HttpResponse:
	"""Grid gallery for a media folder with lightweight fullscreen viewer."""
	try:
		target = get_folder_path(folder)
		safe_name = validate_folder_name(folder)
	except (ValueError, FileNotFoundError):
		raise Http404("Folder not found")
	
	root = wallpapers_root()
	title, year_int = parse_folder_name(safe_name)
	year_display = str(year_int) if year_int is not None else ""

	try:
		files = list_image_files(target)
	except PermissionError:
		files = []

	root = wallpapers_root()
	cover_file = find_cover_filename(target, files)
	cover_url = wallpaper_url(safe_name, cover_file, root=root) if cover_file else None
	cover_thumb_url = thumbnail_url(safe_name, cover_file, width=420, root=root) if cover_file else None
	choose_url = reverse('choose:folder', kwargs={'folder': safe_name})

	images = [
		{
			'name': name,
			'url': wallpaper_url(safe_name, name, root=root),
			'thumb_url': thumbnail_url(safe_name, name, width=512, root=root),
		}
		for name in files
	]

	context = {
		'folder': safe_name,
		'title': title,
		'year': year_display,
		'year_raw': year_int,
		'cover_url': cover_url,
		'cover_thumb_url': cover_thumb_url,
		'choose_url': choose_url,
		'images': images,
		'root': str(root),
	}
	return render(request, 'choose/gallery.html', context)


def folder(request: HttpRequest, folder: str) -> HttpResponse:
	"""Detail page for a media folder: show a two-pane chooser UI with sidebar and viewport."""
	try:
		target = get_folder_path(folder)
		safe_name = validate_folder_name(folder)
	except (ValueError, FileNotFoundError):
		raise Http404("Folder not found")
	
	root = wallpapers_root()

	# Collect image files (jpg/jpeg/png/webp), ordered by filename
	images: list[dict] = []
	try:
		files = list_image_files(target)
		# Fetch existing decisions in bulk
		decisions_qs = ImageDecision.objects.filter(folder=safe_name, filename__in=files)
		decision_map = {d.filename: d.decision for d in decisions_qs}
		for name in files:
			img_url = wallpaper_url(safe_name, name, root=root)
			images.append({
				'name': name,
				'url': img_url,
				'thumb_url': thumbnail_url(safe_name, name, width=320, root=root),
				'decision': decision_map.get(name, ''),
			})
	except PermissionError:
		images = []

	# Initial selection prioritises resumed progress, then first undecided from that point forward
	selected_index = -1
	progress = FolderProgress.objects.filter(folder=safe_name).first()
	start_index = 0
	if progress and images:
		anchor_idx = -1
		if progress.last_classified_name:
			for i, img in enumerate(images):
				if img['name'] == progress.last_classified_name:
					anchor_idx = i
					break
		if anchor_idx != -1:
			start_index = anchor_idx + 1
		elif progress.keep_count:
			start_index = progress.keep_count
	if images:
		if start_index >= len(images):
			start_index = len(images) - 1
		if start_index < 0:
			start_index = 0
		for idx in range(start_index, len(images)):
			if not images[idx].get('decision'):
				selected_index = idx
				break
		if selected_index == -1:
			selected_index = start_index if images else -1

	context = {
		'folder': safe_name,
		'images': images,
		'selected_index': selected_index,
		'selected_image_url': images[selected_index]['url'] if images and selected_index >= 0 else '',
		'selected_image_name': images[selected_index]['name'] if images and selected_index >= 0 else '',
		'root': str(root),
		'path': str(target),
	}
	return render(request, 'choose/folder.html', context)


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
		data = json.loads(request.body.decode('utf-8')) if request.body else {}
	except Exception:
		return JsonResponse({"error": "invalid_json"}, status=400)
	filename = (data.get('filename') or '').strip()
	decision = (data.get('decision') or '').strip()
	if not filename:
		return JsonResponse({"error": "missing_filename"}, status=400)
	if decision not in (ImageDecision.DECISION_KEEP, ImageDecision.DECISION_DELETE, ""):
		return JsonResponse({"error": "invalid_decision"}, status=400)
	if decision == "":
		ImageDecision.objects.filter(folder=safe_name, filename=filename).delete()
		return JsonResponse({"ok": True, "folder": safe_name, "filename": filename, "decision": ""})
	obj, _created = ImageDecision.objects.update_or_create(
		folder=safe_name, filename=filename,
		defaults={"decision": decision}
	)
	return JsonResponse({"ok": True, "folder": obj.folder, "filename": obj.filename, "decision": obj.decision})


@require_POST
def save_api(request: HttpRequest, folder: str) -> JsonResponse:
	"""Apply decisions: delete 'delete' images, and rename kept images to close gaps using EXTRACT_IMAGE_PATTERN counter.

	Undecided images are treated as 'keep'. Files are not moved between folders, only renamed in-place.
	"""
	try:
		safe_name = validate_folder_name(folder)
		target = get_folder_path(folder)
	except ValueError:
		return JsonResponse({"error": "invalid_folder"}, status=400)
	except FileNotFoundError:
		return JsonResponse({"error": "not_found"}, status=404)

	root = wallpapers_root()

	# Gather files ordered by filename - use list_image_files utility
	try:
		files = list_image_files(target)
	except PermissionError:
		return JsonResponse({"error": "permission_denied"}, status=403)

	# Decisions map and existing progress
	decisions_qs = ImageDecision.objects.filter(folder=safe_name)
	decisions = list(decisions_qs.order_by('decided_at', 'filename'))
	dmap = {d.filename: d.decision for d in decisions}
	indices_by_name = {name: idx for idx, name in enumerate(files)}
	previous_progress = FolderProgress.objects.filter(folder=safe_name).first()
	prev_keep_count = previous_progress.keep_count if previous_progress else 0

	to_delete = [name for name in files if dmap.get(name) == ImageDecision.DECISION_DELETE]
	to_keep = [name for name in files if name not in to_delete]

	# Delete marked files
	delete_errors: list[str] = []
	for name in to_delete:
		p = target / name
		try:
			if p.exists() and p.is_file():
				os.remove(p)
		except Exception as e:
			delete_errors.append(f"{name}: {e}")

	# Prepare renames for kept files to close gaps
	# Parse title/year from folder name using utility function
	title, year = parse_title_year_from_folder(safe_name)

	pattern = getattr(settings, 'EXTRACT_IMAGE_PATTERN', '{{ title }} 〜 {{ counter|pad:4 }}.jpg')

	# First, move all kept files to temporary names to avoid collisions
	tmp_map: dict[Path, Path] = {}
	ordered_originals: list[Path] = []
	for idx, name in enumerate(to_keep, start=1):
		src = target / name
		tmp = target / f".{idx:04d}.renametmp.{os.getpid()}_{idx}{src.suffix.lower()}"
		try:
			if src.exists():
				os.rename(src, tmp)
				tmp_map[src] = tmp
				ordered_originals.append(src)
		except Exception as e:
			# If temp rename fails, abort and report
			return JsonResponse({"error": "temp_rename_failed", "file": name, "detail": str(e)}, status=500)

	# Then, rename temps to final names with updated counters
	# Counter resets per (season, episode). If not present, single group.
	rename_errors: list[str] = []
	counters: dict[tuple[str, str], int] = {}
	final_keep_names: list[str] = []

	for original_src in ordered_originals:
		tmp = tmp_map.get(original_src)
		if tmp is None:
			continue
		# Parse season/episode from original filename
		m = SEASON_EPISODE_RE.search(original_src.stem)
		season = m.group('season') if m else ''
		episode = m.group('episode') if m else ''
		key = (season, episode)
		current = counters.get(key, 0) + 1
		counters[key] = current
		values = {
			'title': title,
			'year': year or '',
			'season': int(season) if season.isdigit() else season,
			'episode': int(episode) if episode.isdigit() else episode,
			'counter': current,
		}
		new_name = render_pattern(pattern, values)
		dest = target / new_name
		try:
			# If destination exists (rare), try to unlink or adjust name
			if dest.exists():
				try:
					os.remove(dest)
				except Exception:
					# Fallback: append suffix using combined key and counter
					stem, ext = os.path.splitext(new_name)
					suffix = f" S{season}E{episode} #{current}".strip()
					dest = target / f"{stem}{suffix}{ext}"
			os.rename(tmp, dest)
			final_keep_names.append(dest.name)
		except Exception as e:
			rename_errors.append(f"{original_src.name} -> {dest.name}: {e}")

	# Clean up any leftover temps on error
	if rename_errors:
		# Attempt to move back any remaining temps
		for tmp in tmp_map.values():
			if tmp.exists():
				try:
					# best-effort cleanup
					os.remove(tmp)
				except Exception:
					pass
		return JsonResponse({"error": "rename_failed", "details": rename_errors, "delete_errors": delete_errors}, status=500)

	# Compute new progress statistics before clearing decisions
	remaining_prev_keep_count = sum(1 for name in files[:prev_keep_count] if name not in to_delete)
	keep_names_beyond_prev = {
		name for name, decision in dmap.items()
		if decision == ImageDecision.DECISION_KEEP and indices_by_name.get(name, len(files)) >= prev_keep_count
	}
	new_processed_count = remaining_prev_keep_count + len(keep_names_beyond_prev)
	if new_processed_count > len(final_keep_names):
		new_processed_count = len(final_keep_names)
	anchor_name = ''
	if new_processed_count > 0 and final_keep_names:
		anchor_index = min(new_processed_count - 1, len(final_keep_names) - 1)
		anchor_name = final_keep_names[anchor_index]
	last_original_name = decisions[-1].filename if decisions else (previous_progress.last_classified_original if previous_progress else '')

	FolderProgress.objects.update_or_create(
		folder=safe_name,
		defaults={
			'last_classified_name': anchor_name,
			'last_classified_original': last_original_name,
			'keep_count': new_processed_count,
		},
	)

	# Decisions are now applied; clear them for this folder
	ImageDecision.objects.filter(folder=safe_name).delete()

	kept_total = sum(counters.values()) if counters else len(to_keep)
	return JsonResponse({
		"ok": True,
		"deleted": len(to_delete),
		"kept": kept_total,
		"delete_errors": delete_errors,
	})
