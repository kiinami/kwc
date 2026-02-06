from __future__ import annotations

import logging
import shutil
import threading
from collections.abc import Callable
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import requests
from django.db import close_old_connections
from django.utils import timezone
from PIL import Image

from .extractor import CancellationToken, CancelledException, ExtractParams, extract
from .models import ExtractionJob

logger = logging.getLogger(__name__)


class JobRunner:
    """Manage extraction job execution and lifecycle in background threads."""

    FINISHED_STATUSES = frozenset(
        {ExtractionJob.Status.DONE, ExtractionJob.Status.ERROR, ExtractionJob.Status.CANCELLED}
    )

    def __init__(
        self,
        *,
        extractor: Callable[..., int] = extract,
        model: type[ExtractionJob] = ExtractionJob,
        thread_factory: Callable[[Callable[[str], None], tuple[str, ...]], threading.Thread] | None = None,
    ) -> None:
        self.extractor = extractor
        self.model = model
        self._thread_factory = thread_factory
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_tokens: dict[str, CancellationToken] = {}
        self._lock = threading.Lock()
        self.finished_statuses = frozenset({model.Status.DONE, model.Status.ERROR, model.Status.CANCELLED})

    def start_job(self, job_id: str) -> None:
        """Launch an extraction job in the background."""
        cancel_token = CancellationToken()
        thread = self._make_thread(job_id)
        with self._lock:
            self._threads[job_id] = thread
            self._cancel_tokens[job_id] = cancel_token
        thread.start()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running extraction job.

        Returns True if the job was running and cancellation was initiated,
        False if the job was not running.
        """
        with self._lock:
            cancel_token = self._cancel_tokens.get(job_id)
            if cancel_token is None:
                return False
            cancel_token.cancel()
            return True

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._threads

    def mark_finished(self, job_id: str) -> None:
        with self._lock:
            self._threads.pop(job_id, None)
            self._cancel_tokens.pop(job_id, None)

    def run_job(self, job_id: str) -> None:
        """Execute an extraction job synchronously.

        Used as the thread target and directly in tests.
        """
        try:
            with self.connection_guard():
                self._execute_job(job_id)
        finally:
            self.mark_finished(job_id)

    @contextmanager
    def connection_guard(self):
        """Ensure database connections are reset around background work."""
        close_old_connections()
        try:
            yield
        finally:
            close_old_connections()

    def _make_thread(self, job_id: str) -> threading.Thread:
        factory = self._thread_factory or self._default_thread_factory
        return factory(self.run_job, (job_id,))

    @staticmethod
    def _default_thread_factory(target: Callable[[str], None], args: tuple[str, ...]) -> threading.Thread:
        return threading.Thread(target=target, args=args, daemon=True)

    def _execute_job(self, job_id: str) -> None:
        job = self._get_job(job_id)
        if job is None:
            return

        job.status = self.model.Status.RUNNING
        job.started_at = timezone.now()
        job.error = ""
        job.current_step = 0
        job.total_steps = 0
        job.total_frames = 0
        job.save(
            update_fields=["status", "started_at", "error", "current_step", "total_steps", "total_frames", "updated_at"]
        )

        params_data = job.params or {}
        video_path = Path(params_data["video"])
        output_dir = Path(params_data.get("output_dir") or job.output_dir)
        trim_intervals = list(params_data.get("trim_intervals") or [])
        image_pattern = str(params_data.get("image_pattern") or "")
        max_workers_value = params_data.get("max_workers")
        if max_workers_value in (None, ""):
            max_workers_value = None
        else:
            try:
                max_workers_value = int(max_workers_value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                max_workers_value = None

        # Get cancellation token
        with self._lock:
            cancel_token = self._cancel_tokens.get(job_id)

        extract_params = ExtractParams(
            video=video_path,
            output_dir=output_dir,
            trim_intervals=trim_intervals,
            title=str(params_data.get("title") or ""),
            image_pattern=image_pattern,
            year=int(params_data["year"]) if params_data.get("year") not in (None, "") else None,
            season=int(params_data["season"]) if params_data.get("season") not in (None, "") else None,
            episode=params_data.get("episode") if params_data.get("episode") not in (None, "") else None,
            max_workers=max_workers_value,
            cancel_token=cancel_token,
        )

        def on_progress(done: int, total: int) -> None:
            self.model.objects.filter(pk=job_id).update(
                total_steps=max(total, 1),
                current_step=done,
                total_frames=done,
                updated_at=timezone.now(),
            )

        try:
            frame_count = self.extractor(params=extract_params, on_progress=on_progress)

            # Download cover image if URL was provided, or copy from source if available
            cover_image_url = params_data.get("cover_image_url", "").strip()
            source_cover_path = params_data.get("source_cover_path", "").strip()

            if cover_image_url:
                self._download_cover_image(cover_image_url, output_dir)
            elif source_cover_path:
                self._copy_cover_image(Path(source_cover_path), output_dir)

            if params_data.get("deduplicate"):
                job.status = self.model.Status.DEDUPLICATING
                job.save(update_fields=["status", "updated_at"])

                threshold_val = params_data.get("deduplicate_threshold")
                try:
                    threshold = float(threshold_val) if threshold_val is not None else 0.9
                except (ValueError, TypeError):
                    threshold = 0.9

                from .deduplication import process_deduplication

                process_deduplication(job, cancel_token, threshold=threshold)

            job.refresh_from_db()
            job.total_frames = frame_count
            if job.total_steps == 0:
                job.total_steps = frame_count
            job.current_step = job.total_steps
            job.status = self.model.Status.DONE
            job.finished_at = timezone.now()
            job.save(
                update_fields=["status", "finished_at", "total_frames", "current_step", "total_steps", "updated_at"]
            )
        except CancelledException:
            logger.info("extract job %s cancelled", job_id)
            self.model.objects.filter(pk=job_id).update(
                status=self.model.Status.CANCELLED,
                error="Job cancelled by user",
                finished_at=timezone.now(),
                updated_at=timezone.now(),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("extract job %s failed", job_id)
            self.model.objects.filter(pk=job_id).update(
                status=self.model.Status.ERROR,
                error=str(exc),
                finished_at=timezone.now(),
                updated_at=timezone.now(),
            )

    def _download_cover_image(self, url: str, output_dir: Path) -> None:
        """Download a cover image from a URL and save it to the output directory."""
        try:
            # Create output directory if it doesn't exist
            output_dir.mkdir(parents=True, exist_ok=True)

            # Download the image
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Open and convert the image
            img = Image.open(BytesIO(response.content))

            # Save as .cover.jpg
            cover_path = output_dir / ".cover.jpg"
            img.convert("RGB").save(cover_path, "JPEG", quality=95)
            logger.info(f"Downloaded cover image to {cover_path}")
        except Exception as e:
            logger.warning(f"Failed to download cover image: {e}")
            # Don't fail the job if cover download fails

    def _copy_cover_image(self, source_path: Path, output_dir: Path) -> None:
        """Copy an existing cover image to the output directory."""
        try:
            if not source_path.exists():
                return

            # Create output directory if it doesn't exist
            output_dir.mkdir(parents=True, exist_ok=True)

            # Determine destination filename
            # If source is explicitly named .cover.*, preserve extension
            # If source is a random image, strictly name it .cover + extension to mark it as cover
            dest_name = ".cover" + source_path.suffix
            dest_path = output_dir / dest_name

            # Always overwrite any existing cover at the destination to ensure the selected cover is applied.

            shutil.copy2(source_path, dest_path)
            logger.info(f"Copied cover image from {source_path} to {dest_path}")
        except Exception as e:
            logger.warning(f"Failed to copy cover image: {e}")

    def _get_job(self, job_id: str) -> ExtractionJob | None:
        try:
            return self.model.objects.get(pk=job_id)  # type: ignore[no-any-return]
        except self.model.DoesNotExist:
            return None


job_runner = JobRunner()
