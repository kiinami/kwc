import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import close_old_connections
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

from .forms import ExtractStartForm
from .extractor import ExtractParams, extract
from .models import ExtractionJob
from .utils import render_pattern


RUNNING_THREADS: dict[str, threading.Thread] = {}
RUNNING_LOCK = threading.Lock()
FINISHED_STATUSES = {ExtractionJob.Status.DONE, ExtractionJob.Status.ERROR}


def _job_summary(job: ExtractionJob) -> dict[str, Any]:
	return {
		"id": job.id,
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


def _launch_job_thread(job_id: str) -> None:
	thread = threading.Thread(target=_run_extract_job, args=(job_id,), daemon=True)
	with RUNNING_LOCK:
		RUNNING_THREADS[job_id] = thread
	thread.start()


def _run_extract_job(job_id: str) -> None:
	close_old_connections()
	try:
		job = ExtractionJob.objects.get(pk=job_id)
	except ExtractionJob.DoesNotExist:
		return

	job.status = ExtractionJob.Status.RUNNING
	job.started_at = timezone.now()
	job.error = ""
	job.current_step = 0
	job.total_steps = 0
	job.total_frames = 0
	job.save(update_fields=["status", "started_at", "error", "current_step", "total_steps", "total_frames", "updated_at"])

	params_data = job.params or {}
	video_path = Path(params_data["video"])
	output_dir = Path(params_data.get("output_dir") or job.output_dir)
	trim_intervals = list(params_data.get("trim_intervals") or [])
	image_pattern = str(params_data.get("image_pattern") or "")

	extract_params = ExtractParams(
		video=video_path,
		output_dir=output_dir,
		trim_intervals=trim_intervals,
		title=str(params_data.get("title") or ""),
		image_pattern=image_pattern,
		year=int(params_data["year"]) if params_data.get("year") not in (None, "") else None,
		season=int(params_data["season"]) if params_data.get("season") not in (None, "") else None,
		episode=params_data.get("episode") if params_data.get("episode") not in (None, "") else None,
	)

	def on_progress(done: int, total: int) -> None:
		ExtractionJob.objects.filter(pk=job_id).update(
			total_steps=max(total, 1),
			current_step=done,
			total_frames=done,
			updated_at=timezone.now(),
		)

	try:
		frame_count = extract(params=extract_params, on_progress=on_progress)
		job.refresh_from_db()
		job.total_frames = frame_count
		if job.total_steps == 0:
			job.total_steps = frame_count
		job.current_step = job.total_steps
		job.status = ExtractionJob.Status.DONE
		job.finished_at = timezone.now()
		job.save(update_fields=["status", "finished_at", "total_frames", "current_step", "total_steps", "updated_at"])
	except Exception as exc:  # pragma: no cover
		logging.getLogger(__name__).exception("extract job %s failed", job_id)
		ExtractionJob.objects.filter(pk=job_id).update(
			status=ExtractionJob.Status.ERROR,
			error=str(exc),
			finished_at=timezone.now(),
			updated_at=timezone.now(),
		)
	finally:
		with RUNNING_LOCK:
			RUNNING_THREADS.pop(job_id, None)
		close_old_connections()


def start(request: HttpRequest) -> HttpResponse:
	if request.method == "POST":
		form = ExtractStartForm(request.POST)
		if form.is_valid():
			job_id = uuid.uuid4().hex
			params = form.cleaned_data.copy()
			params["trim_intervals"] = form.cleaned_data.get("trim_intervals", [])

			root = Path(getattr(settings, "WALLPAPERS_FOLDER", settings.BASE_DIR / "extracted"))
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

			ExtractionJob.objects.create(
				id=job_id,
				params=params,
				output_dir=str(output_dir),
			)

			_launch_job_thread(job_id)

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
			"folder_pattern": getattr(settings, "EXTRACT_FOLDER_PATTERN", "{title}"),
			"image_pattern": getattr(settings, "EXTRACT_IMAGE_PATTERN", "{title}_{counter:04}.jpg"),
		},
	)


def job(request: HttpRequest, job_id: str) -> HttpResponse:
	job_obj = get_object_or_404(ExtractionJob, pk=job_id)
	total_known = job_obj.total_steps > 0
	context = {
		"job_id": job_obj.id,
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
	- path: absolute path to list; defaults to '/'
	- dirs_only: '1' to return only directories
	"""
	raw = request.GET.get("path") or "/"
	dirs_only = request.GET.get("dirs_only") == "1"
	# Security: normalize and restrict to absolute paths; optionally restrict to allowlist here
	path = os.path.abspath(raw)
	if not os.path.isabs(path):
		return JsonResponse({"error": "path_must_be_absolute"}, status=400)
	if not os.path.exists(path):
		return JsonResponse({"error": "not_found"}, status=404)
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
		return JsonResponse({"path": path, "entries": entries})
	except PermissionError:
		return JsonResponse({"error": "permission_denied"}, status=403)
	except OSError as e:
		return JsonResponse({"error": str(e)}, status=500)
