import os
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

try:
	# Optional import guard; will raise at runtime if missing
	from guessit import guessit as _guessit
except Exception:  # pragma: no cover
	_guessit = None

import contextlib

from .forms import ExtractStartForm
from .job_runner import JobRunner, job_runner
from .models import ExtractionJob
from .utils import render_pattern

FINISHED_STATUSES = JobRunner.FINISHED_STATUSES


def _job_summary(job: ExtractionJob) -> dict[str, Any]:
	return {
		"id": job.id,
		"name": job.name,
		"status": job.status,
		"status_label": job.get_status_display(),
		"status_class": job.status_css(),
		"percent": job.percent,
		"finished": job.status in FINISHED_STATUSES,
		"done": job.status == ExtractionJob.Status.DONE,
	}


def _format_duration(job: ExtractionJob) -> str:
	if job.started_at:
		end = job.finished_at or timezone.now()
		return f"{max(0.0, (end - job.started_at).total_seconds()):.1f}s"
	return "—"



def start(request: HttpRequest) -> HttpResponse:
	if request.method == "POST":
		form = ExtractStartForm(request.POST)
		if form.is_valid():
			job_id = uuid.uuid4().hex
			params = form.cleaned_data.copy()
			params["trim_intervals"] = form.cleaned_data.get("trim_intervals", [])
			params["cover_image_url"] = form.cleaned_data.get("cover_image_url", "")

			root = Path(settings.EXTRACTION_FOLDER)
			folder_pattern = settings.EXTRACT_FOLDER_PATTERN
			folder_rel = render_pattern(
				folder_pattern,
				{
					"title": params.get("title", ""),
					"year": params.get("year", ""),
					"season": params.get("season", ""),
					"episode": params.get("episode", ""),
				},
			).strip()
			if not folder_rel:
				folder_rel = params.get("title") or job_id
			output_dir = root / folder_rel
			params["output_dir"] = str(output_dir)
			params["image_pattern"] = settings.EXTRACT_IMAGE_PATTERN

			# Extract filename from video path for job name
			video_path = params.get("video", "")
			job_name = os.path.basename(video_path) if video_path else ""

			# Check if there is an existing cover image in the library folder
			try:
				from choose.utils import find_cover_filename  # noqa: PLC0415
				library_root = Path(settings.WALLPAPERS_FOLDER)
				library_dir = library_root / folder_rel
				if library_dir.exists() and library_dir.is_dir():
					cover_name = find_cover_filename(library_dir)
					if cover_name:
						params["source_cover_path"] = str(library_dir / cover_name)
			except Exception:  # pragma: no cover
				# Fail silently if we can't find/access the library folder
				pass

			ExtractionJob.objects.create(
				id=job_id,
				name=job_name,
				params=params,
				output_dir=str(output_dir),
			)

			job_runner.start_job(job_id)

			jobs = request.session.get("extract_jobs", [])
			if job_id not in jobs:
				jobs.append(job_id)
				jobs = jobs[-5:]
				request.session["extract_jobs"] = jobs
				request.session.modified = True

			return redirect("extract:job", job_id=job_id)
	else:
		form = ExtractStartForm()

	return render(
		request,
		"extract/start.html",
		{
			"form": form,
			"folder_pattern": settings.EXTRACT_FOLDER_PATTERN,
			"image_pattern": settings.EXTRACT_IMAGE_PATTERN,
			"file_picker_start_path": settings.FILE_PICKER_START_PATH,
		},
	)


def job(request: HttpRequest, job_id: str) -> HttpResponse:
	job_obj = get_object_or_404(ExtractionJob, pk=job_id)
	total_known = job_obj.total_steps > 0
	
	# Extract folder name from output_dir for gallery link
	folder_name = os.path.basename(job_obj.output_dir.rstrip(os.sep))
	gallery_url = reverse('choose:inbox_gallery', kwargs={'folder': folder_name})
	
	context = {
		"job_id": job_obj.id,
		"job_name": job_obj.name,
		"status": job_obj.status,
		"status_label": job_obj.get_status_display(),
		"status_class": job_obj.status_css(),
		"error_message": job_obj.error or "",
		"percent": job_obj.percent,
		"total": job_obj.total_steps if total_known else None,
		"current": job_obj.current_step if total_known else None,
		"elapsed": job_obj.elapsed_seconds,
		"is_finished": job_obj.status in FINISHED_STATUSES,
		"is_done": job_obj.status == ExtractionJob.Status.DONE,
		"is_error": job_obj.status == ExtractionJob.Status.ERROR,
		"gallery_url": gallery_url,
		"results": {
			"total_frames": job_obj.total_frames,
			"time_taken": _format_duration(job_obj),
			"output_dir": job_obj.output_dir,
		},
	}
	return render(request, "extract/job.html", context)


def job_api(request: HttpRequest, job_id: str) -> JsonResponse:
	job_obj = get_object_or_404(ExtractionJob, pk=job_id)
	total_known = job_obj.total_steps > 0
	payload = {
		"name": job_obj.name,
		"status": job_obj.status,
		"status_label": job_obj.get_status_display(),
		"status_class": job_obj.status_css(),
		"percent": job_obj.percent,
		"current": job_obj.current_step if total_known else None,
		"total": job_obj.total_steps if total_known else None,
		"total_frames": job_obj.total_frames,
		"elapsed_seconds": job_obj.elapsed_seconds,
		"finished": job_obj.status in FINISHED_STATUSES,
		"done": job_obj.status == ExtractionJob.Status.DONE,
		"error": job_obj.error or "",
		"time_taken": _format_duration(job_obj),
		"output_dir": job_obj.output_dir,
	}
	return JsonResponse(payload)


@require_POST
def cancel_job(request: HttpRequest, job_id: str) -> JsonResponse:
	"""Cancel a running extraction job."""
	job_obj = get_object_or_404(ExtractionJob, pk=job_id)
	
	# Check if job is already finished
	if job_obj.status in FINISHED_STATUSES:
		return JsonResponse({"success": False, "error": "Job already finished"}, status=400)
	
	# Immediately mark the job as cancelling in the database
	job_obj.status = ExtractionJob.Status.CANCELLING
	job_obj.save(update_fields=["status", "updated_at"])
	
	# Try to cancel the job
	was_running = job_runner.cancel_job(job_id)
	
	if not was_running:
		# Job wasn't actually running, mark as fully cancelled
		job_obj.status = ExtractionJob.Status.CANCELLED
		job_obj.error = "Job cancelled by user"
		job_obj.finished_at = timezone.now()
		job_obj.save(update_fields=["status", "error", "finished_at", "updated_at"])
	
	return JsonResponse({"success": True, "status": job_obj.status})


def index(request: HttpRequest) -> HttpResponse:
	jobs = [
		_job_summary(job)
		for job in ExtractionJob.objects.all()[:50]
	]
	return render(request, "extract/index.html", {"jobs": jobs})


def jobs_api(request: HttpRequest) -> JsonResponse:
	jobs = [
		_job_summary(job)
		for job in ExtractionJob.objects.all()[:50]
	]
	return JsonResponse({"jobs": jobs})


@require_GET
def guess_api(request: HttpRequest) -> JsonResponse:
	"""Guess media metadata from a filename using guessit.

	Query params:
	- path: full file path (we will use the basename)
	- name: optional explicit name to parse (takes precedence over path)
	"""
	if _guessit is None:
		return JsonResponse({"error": "guessit_not_installed"}, status=500)

	name = request.GET.get("name")
	path = request.GET.get("path")
	target = (name or "").strip()
	if not target:
		if not path:
			return JsonResponse({"error": "missing_name_or_path"}, status=400)
		target = os.path.basename(path)
	try:
		info = _guessit(target)
	except Exception as e:  # pragma: no cover
		return JsonResponse({"error": str(e)}, status=500)

	# Extract desired fields with sensible coercion
	title = info.get("title") or ""
	year = info.get("year")
	season = info.get("season")
	episode = info.get("episode")
	if isinstance(episode, list) and episode:
		episode = episode[0]
	# Some releases include episode title; prefer numeric episode if available, otherwise title
	episode_title = info.get("episode_title")
	if episode in (None, "") and episode_title:
		episode = str(episode_title)

	payload = {
		"title": str(title),
		"year": int(year) if isinstance(year, int) else (year or ""),
		"season": int(season) if isinstance(season, int) else (season or ""),
		"episode": str(episode) if episode not in (None, "") else "",
		"type": str(info.get("type") or ""),
	}
	return JsonResponse(payload)


@require_GET
def browse_api(request: HttpRequest) -> JsonResponse:
	"""List directories and files under a given absolute path root.

	Query params:
	- path: absolute path to list; defaults to FILE_PICKER_START_PATH setting
	- dirs_only: '1' to return only directories
	"""
	raw = request.GET.get("path") or settings.FILE_PICKER_START_PATH
	dirs_only = request.GET.get("dirs_only") == "1"
	# Security: normalize and restrict to absolute paths; optionally restrict to allowlist here
	path = os.path.abspath(raw)
	if not os.path.isabs(path):
		response = JsonResponse({"error": "path_must_be_absolute"}, status=400)
		response['Cache-Control'] = 'no-store'
		return response
	if not os.path.exists(path):
		response = JsonResponse({"error": "not_found"}, status=404)
		response['Cache-Control'] = 'no-store'
		return response
	try:
		entries = []
		with os.scandir(path) as it:
			for e in it:
				if dirs_only and not e.is_dir():
					continue
				entries.append({
					"name": e.name,
					"path": os.path.join(path, e.name),
					"is_dir": e.is_dir(),
				})
		# Sort dirs first then files, by name
		entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
		response = JsonResponse({"path": path, "entries": entries})
		response['Cache-Control'] = 'no-store'
		return response
	except PermissionError:
		response = JsonResponse({"error": "permission_denied"}, status=403)
		response['Cache-Control'] = 'no-store'
		return response
	except OSError as e:
		response = JsonResponse({"error": str(e)}, status=500)
		response['Cache-Control'] = 'no-store'
		return response


@require_GET
def folders_api(request: HttpRequest) -> JsonResponse:
	"""List existing wallpaper folders with their metadata.

	Returns a list of folders that can be used for selection in the extract form.
	"""
	from choose.utils import extraction_root, list_media_folders  # noqa: PLC0415

	# Get folders from both library (wallpapers) and inbox (extraction)
	library_folders, _ = list_media_folders()
	inbox_folders, _ = list_media_folders(root=extraction_root())

	# Merge lists, keyed by folder name to avoid duplicates
	# Library takes precedence for metadata if both exist
	seen = set()
	merged = []

	for f in library_folders:
		seen.add(f["name"])
		merged.append(f)

	for f in inbox_folders:
		if f["name"] not in seen:
			seen.add(f["name"])
			merged.append(f)

	# Re-sort combined list
	merged.sort(
		key=lambda x: (x["year_sort"], x["mtime"], x["name"].lower()), reverse=True
	)

	# Return folder data including cover URLs for the dropdown
	result = [
		{
			"name": f["name"],
			"title": f["title"],
			"year": f["year_raw"],  # Return raw int or None
			"cover_url": f["cover_url"],
			"cover_thumb_url": f["cover_thumb_url"],
		}
		for f in merged
	]
	return JsonResponse({"folders": result})


@require_GET
def tmdb_search_api(request: HttpRequest) -> JsonResponse:
	"""Search TMDB for movies and TV shows.

	Query params:
	- query: The title to search for (required)
	- year: Optional year to filter results
	"""
	from django.conf import settings  # noqa: PLC0415

	from . import tmdb  # noqa: PLC0415

	if not settings.TMDB_API_KEY:
		return JsonResponse({"error": "tmdb_not_configured"}, status=500)

	query = request.GET.get("query", "").strip()
	if not query:
		return JsonResponse({"error": "missing_query"}, status=400)

	year_str = request.GET.get("year", "").strip()
	year = None
	if year_str:
		with contextlib.suppress(ValueError):
			year = int(year_str)

	try:
		tmdb.configure_api_key(settings.TMDB_API_KEY)
		results = tmdb.search_multi(query, year=year)
		return JsonResponse({"results": results})
	except RuntimeError as e:
		return JsonResponse({"error": str(e)}, status=500)


@require_GET
def tmdb_posters_api(request: HttpRequest) -> JsonResponse:
	"""Get posters for a specific movie or TV show.

	Query params:
	- media_type: Either "movie" or "tv" (required)
	- media_id: The TMDB ID of the media (required)
	"""
	from django.conf import settings  # noqa: PLC0415

	from . import tmdb  # noqa: PLC0415

	if not settings.TMDB_API_KEY:
		return JsonResponse({"error": "tmdb_not_configured"}, status=500)

	media_type = request.GET.get("media_type", "").strip()
	media_id_str = request.GET.get("media_id", "").strip()

	if not media_type or not media_id_str:
		return JsonResponse({"error": "missing_parameters"}, status=400)

	try:
		media_id = int(media_id_str)
	except ValueError:
		return JsonResponse({"error": "invalid_media_id"}, status=400)

	try:
		tmdb.configure_api_key(settings.TMDB_API_KEY)
		posters = tmdb.get_posters(media_type, media_id)
		return JsonResponse({"posters": posters})
	except ValueError as e:
		return JsonResponse({"error": str(e)}, status=400)
	except RuntimeError as e:
		return JsonResponse({"error": str(e)}, status=500)
