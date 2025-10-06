from django.shortcuts import render, redirect
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.urls import reverse
from django.conf import settings
from pathlib import Path
import os
import re
from urllib.parse import quote
import json
from .models import ImageDecision
from django.views.decorators.http import require_POST
from extract.utils import render_pattern


def _get_wallpapers_root() -> Path:
	return Path(getattr(settings, 'WALLPAPERS_FOLDER', getattr(settings, 'EXTRACT_DEFAULT_ROOT', settings.BASE_DIR / 'extracted')))


def index(request: HttpRequest) -> HttpResponse:
	"""Home page: list media folders inside wallpapers root."""
	root = _get_wallpapers_root()
	entries: list[dict] = []
	if root.exists() and root.is_dir():
		try:
			with os.scandir(root) as it:
				for e in it:
					if not e.is_dir():
						continue
					# Skip hidden folders (dot-prefixed)
					if e.name.startswith('.'):
						continue
					folder_name = e.name
					# Parse title and year from pattern: {title} ({year})
					title = folder_name
					year = ""
					if folder_name.endswith(')'):
						try:
							left = folder_name.rfind(' (')
							if left != -1 and folder_name.endswith(')'):
								maybe_year = folder_name[left + 2:-1]
								if maybe_year.isdigit():
									title = folder_name[:left]
									year = maybe_year
						except Exception:
							title = folder_name
							year = ""
					year_int = int(year) if year.isdigit() else None

					# Determine cover image (prefer .cover.jpg/.cover.png, else first image)
					folder_path = root / folder_name
					cover_file = None
					for cand in ('.cover.jpg', '.cover.jpeg', '.cover.png', '.cover.webp'):
						p = folder_path / cand
						if p.exists() and p.is_file():
							cover_file = p.name
							break
					if cover_file is None:
						exts = {'.jpg', '.jpeg', '.png', '.webp'}
						try:
							files = []
							with os.scandir(folder_path) as fit:
								for fe in fit:
									if fe.is_file() and not fe.name.startswith('.'):
										_, ext = os.path.splitext(fe.name)
										if ext.lower() in exts:
											files.append(fe.name)
							files.sort(key=lambda n: n.lower())
							if files:
								cover_file = files[0]
						except PermissionError:
							pass

					cover_url = None
					if cover_file:
						# Serve via dev static mount at /wallpapers/
						cover_url = f"/wallpapers/{quote(folder_name)}/{quote(cover_file)}"

					# Folder mtime as secondary recency signal
					try:
						mtime = e.stat().st_mtime_ns
					except Exception:
						mtime = 0

					entries.append({
						'name': folder_name,
						'title': title,
						'year': year,
						'year_sort': (year_int if year_int is not None else -1),
						'mtime': mtime,
						'url': reverse('choose:folder', kwargs={'folder': folder_name}),
						'cover_url': cover_url,
					})
		except PermissionError:
			entries = []
	# Sort by year desc (missing year last), then by modification time desc, then by name
	entries.sort(key=lambda x: (x['year_sort'], x['mtime'], x['name'].lower()), reverse=True)
	return render(request, 'choose/index.html', {"folders": entries, "root": str(root)})


def folder(request: HttpRequest, folder: str) -> HttpResponse:
	"""Detail page for a media folder: show a two-pane chooser UI with sidebar and viewport."""
	root = _get_wallpapers_root()
	# Prevent path traversal; only allow direct child folders under the root
	safe_name = os.path.basename(folder)
	if safe_name != folder:
		raise Http404("Invalid folder name")
	# Disallow hidden folders
	if safe_name.startswith('.'):
		raise Http404("Folder not found")
	target = root / safe_name
	if not target.exists() or not target.is_dir():
		raise Http404("Folder not found")

	# Collect image files (jpg/jpeg/png/webp), ordered by filename
	exts = {'.jpg', '.jpeg', '.png', '.webp'}
	images: list[dict] = []
	try:
		files: list[str] = []
		with os.scandir(target) as it:
			for e in it:
				if e.is_file() and not e.name.startswith('.'):
					_, ext = os.path.splitext(e.name)
					if ext.lower() in exts:
						files.append(e.name)
		files.sort(key=lambda n: n.lower())
		# Fetch existing decisions in bulk
		decisions_qs = ImageDecision.objects.filter(folder=safe_name, filename__in=files)
		decision_map = {d.filename: d.decision for d in decisions_qs}
		for name in files:
			images.append({
				'name': name,
				'url': f"/wallpapers/{quote(safe_name)}/{quote(name)}",
				'decision': decision_map.get(name, ''),
			})
	except PermissionError:
		images = []

	# Initial selection: first UNDECIDED image; if all decided, fall back to first
	selected_index = -1
	for i, img in enumerate(images):
		if not img.get('decision'):
			selected_index = i
			break
	if selected_index == -1:
		selected_index = 0 if images else -1

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


@require_POST
def decide_api(request: HttpRequest, folder: str) -> JsonResponse:
	"""Persist a keep/delete decision for an image in a given folder.

	JSON body: { "filename": str, "decision": "keep"|"delete" }
	"""
	safe_name = os.path.basename(folder)
	if safe_name != folder or safe_name.startswith('.'):
		return JsonResponse({"error": "invalid_folder"}, status=400)
	try:
		data = json.loads(request.body.decode('utf-8')) if request.body else {}
	except Exception:
		return JsonResponse({"error": "invalid_json"}, status=400)
	filename = (data.get('filename') or '').strip()
	decision = (data.get('decision') or '').strip()
	if not filename:
		return JsonResponse({"error": "missing_filename"}, status=400)
	if decision not in (ImageDecision.DECISION_KEEP, ImageDecision.DECISION_DELETE):
		return JsonResponse({"error": "invalid_decision"}, status=400)
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
	safe_name = os.path.basename(folder)
	if safe_name != folder or safe_name.startswith('.'):
		return JsonResponse({"error": "invalid_folder"}, status=400)
	root = _get_wallpapers_root()
	target = root / safe_name
	if not target.exists() or not target.is_dir():
		return JsonResponse({"error": "not_found"}, status=404)

	# Gather files ordered by filename
	exts = {'.jpg', '.jpeg', '.png', '.webp'}
	files: list[str] = []
	with os.scandir(target) as it:
		for e in it:
			if e.is_file() and not e.name.startswith('.'):
				_, ext = os.path.splitext(e.name)
				if ext.lower() in exts:
					files.append(e.name)
	files.sort(key=lambda n: n.lower())

	# Decisions map
	decisions_qs = ImageDecision.objects.filter(folder=safe_name)
	dmap = {d.filename: d.decision for d in decisions_qs}

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
	# Parse title/year from folder name: "Title (Year)"
	title = safe_name
	year: str | int | None = None
	if safe_name.endswith(')'):
		try:
			left = safe_name.rfind(' (')
			if left != -1 and safe_name.endswith(')'):
				maybe_year = safe_name[left + 2:-1]
				if maybe_year.isdigit():
					title = safe_name[:left]
					year = int(maybe_year)
		except Exception:
			title = safe_name
			year = None

	pattern = getattr(settings, 'EXTRACT_IMAGE_PATTERN', '{{ title }} 〜 {{ counter|pad:4 }}.jpg')

	# First, move all kept files to temporary names to avoid collisions
	tmp_map: dict[Path, Path] = {}
	for idx, name in enumerate(to_keep, start=1):
		src = target / name
		tmp = target / f".{idx:04d}.renametmp.{os.getpid()}_{idx}{src.suffix.lower()}"
		try:
			if src.exists():
				os.rename(src, tmp)
				tmp_map[src] = tmp
		except Exception as e:
			# If temp rename fails, abort and report
			return JsonResponse({"error": "temp_rename_failed", "file": name, "detail": str(e)}, status=500)

	# Then, rename temps to final names with updated counters
	# Counter resets per (season, episode). If not present, single group.
	rename_errors: list[str] = []
	se_re = re.compile(r"S(?P<season>\d{1,3})E(?P<episode>[A-Za-z0-9]{1,6})", re.IGNORECASE)
	counters: dict[tuple[str, str], int] = {}

	for original_src, tmp in tmp_map.items():
		# Parse season/episode from original filename
		m = se_re.search(original_src.stem)
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
		except Exception as e:
			rename_errors.append(f"{original_src.name} -> {dest.name}: {e}")

	# Clean up any leftover temps on error
	if rename_errors:
		# Attempt to move back any remaining temps
		for _, tmp in tmp_map.items():
			if tmp.exists():
				try:
					# best-effort cleanup
					os.remove(tmp)
				except Exception:
					pass
		return JsonResponse({"error": "rename_failed", "details": rename_errors, "delete_errors": delete_errors}, status=500)

	# Decisions are now applied; clear them for this folder
	ImageDecision.objects.filter(folder=safe_name).delete()

	kept_total = sum(counters.values()) if counters else len(to_keep)
	return JsonResponse({
		"ok": True,
		"deleted": len(to_delete),
		"kept": kept_total,
		"delete_errors": delete_errors,
	})
