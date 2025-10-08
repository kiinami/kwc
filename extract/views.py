import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
import os
import json

try:
	# Optional import guard; will raise at runtime if missing
	from guessit import guessit as _guessit
except Exception:  # pragma: no cover
	_guessit = None

from .forms import ExtractStartForm
from .extractor import ExtractParams, extract
from django.conf import settings
from .utils import render_pattern


@dataclass
class ExtractJob:
	id: str
	params: dict
	started_at: float = field(default_factory=time.time)
	finished_at: Optional[float] = None
	total_steps: int = 0
	current_step: int = 0
	status: str = "pending"  # pending|running|done|error
	error: Optional[str] = None
	total_frames: int = 0


_JOBS: dict[str, ExtractJob] = {}
_JOBS_LOCK = threading.Lock()


def _run_extract_job(job_id: str):
	with _JOBS_LOCK:
		job = _JOBS.get(job_id)
		if not job:
			return
		job.status = "running"

	# Run real extraction while updating progress
	try:
		p = job.params
		params = ExtractParams(
			video=Path(p["video"]),
			output_dir=Path(p["output_dir"]),
			trim_intervals=list(p.get("trim_intervals") or []),
			title=str(p.get("title") or ""),
			image_pattern=str(p.get("image_pattern") or ""),
			year=int(p.get("year")) if p.get("year") not in (None, "") else None,
			season=int(p.get("season")) if p.get("season") not in (None, "") else None,
			episode=p.get("episode") if p.get("episode") not in (None, "") else None,
		)

		# First, we need to know total keyframes to set total_steps more accurately.
		# We'll do a quick probe via extractor.get_iframe_timestamps lazily in callback
		# by setting total on first progress callback, but we can also set a rough default.

		def on_progress(done: int, total: int):
			with _JOBS_LOCK:
				job.total_steps = max(total, 1)
				job.current_step = done
				job.total_frames = done

		count = extract(params=params, on_progress=on_progress)
		with _JOBS_LOCK:
			job.total_frames = count
			job.current_step = job.total_steps
			job.status = "done"
			job.finished_at = time.time()
	except Exception as e:  # pragma: no cover
		import logging
		logging.getLogger(__name__).exception("extract job %s failed", job_id)
		with _JOBS_LOCK:
			job.status = "error"
			job.error = str(e)
			job.finished_at = time.time()


def start(request: HttpRequest) -> HttpResponse:
	if request.method == "POST":
		form = ExtractStartForm(request.POST)
		if form.is_valid():
			job_id = uuid.uuid4().hex
			with _JOBS_LOCK:
				params = form.cleaned_data.copy()
				# Ensure trim_intervals is a list post-cleaning
				params["trim_intervals"] = form.cleaned_data.get("trim_intervals", [])
				# Compute output directory from settings and title
				# Use unified wallpapers root
				root = Path(getattr(settings, 'WALLPAPERS_FOLDER', settings.BASE_DIR / 'extracted'))
				folder_pattern = settings.EXTRACT_FOLDER_PATTERN
				folder_rel = render_pattern(
					folder_pattern,
					{
						"title": params.get("title", ""),
						"year": params.get("year", ""),
						"season": params.get("season", ""),
						"episode": params.get("episode", ""),
					}
				)
				output_dir = root / folder_rel
				params["output_dir"] = str(output_dir)
				# Pass image filename pattern
				params["image_pattern"] = settings.EXTRACT_IMAGE_PATTERN
				_JOBS[job_id] = ExtractJob(id=job_id, params=params)
			t = threading.Thread(target=_run_extract_job, args=(job_id,), daemon=True)
			t.start()
			# Track user's recent jobs in session for easy resume
			jobs = request.session.get("extract_jobs", [])
			if job_id not in jobs:
				jobs.append(job_id)
				# Keep only the last 5
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
	with _JOBS_LOCK:
		job = _JOBS.get(job_id)
	if not job:
		return redirect("extract:start")
	pct = int(job.current_step * 100 / max(1, job.total_steps))
	elapsed = time.time() - job.started_at
	context = {
		"job_id": job_id,
		"status": job.status,
		"percent": pct,
		"total": job.total_steps,
		"current": job.current_step,
		"elapsed": elapsed,
		"is_done": job.status == "done",
		"results": {
			"total_frames": job.total_frames,
			"time_taken": f"{(job.finished_at or time.time()) - job.started_at:.1f}s",
			"output_dir": job.params.get("output_dir"),
		},
	}
	return render(request, "extract/job.html", context)


# Index covers both running and completed jobs.

def job_api(request: HttpRequest, job_id: str) -> JsonResponse:
	with _JOBS_LOCK:
		job = _JOBS.get(job_id)
		if not job:
			return JsonResponse({"error": "not_found"}, status=404)
		total_known = job.total_steps > 0
		pct = int(job.current_step * 100 / max(1, job.total_steps or 1)) if total_known else 0
		payload = {
			"status": job.status,
			"current": job.current_step,
			"total": job.total_steps if total_known else None,
			"percent": pct,
			"total_frames": job.total_frames,
			"total_known": total_known,
		}
		if job.status == "done":
			payload["done"] = True
	return JsonResponse(payload)


# Job view shows progress and final state


def index(request):
	# Dashboard view: show create button + all jobs (running and completed)
	with _JOBS_LOCK:
		jobs_list = list(_JOBS.values())
	jobs_list.sort(key=lambda j: j.started_at, reverse=True)
	rows = []
	for j in jobs_list:
		percent = int(j.current_step * 100 / max(1, j.total_steps))
		rows.append(
			{
				"id": j.id,
				"status": j.status,
				"percent": percent,
			}
		)
	return render(request, 'extract/index.html', {"jobs": rows})


def jobs_api(request: HttpRequest) -> JsonResponse:
	with _JOBS_LOCK:
		jobs_list = list(_JOBS.values())
	jobs_list.sort(key=lambda j: j.started_at, reverse=True)
	data = []
	for j in jobs_list:
		percent = int(j.current_step * 100 / max(1, j.total_steps))
		data.append({"id": j.id, "status": j.status, "percent": percent})
	return JsonResponse({"jobs": data})


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


	# browse_mkdir_api was removed as unused to simplify the API surface
