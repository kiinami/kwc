import logging
from typing import Any

from django.apps import AppConfig
from django.db import OperationalError, ProgrammingError
from django.db.backends.signals import connection_created
from django.utils import timezone


class ExtractConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'extract'
    _interrupted_jobs_marked = False

    def ready(self) -> None:
        super().ready()
        connection_created.connect(self._on_connection_ready, dispatch_uid='extract.mark_interrupted_jobs')

    def _on_connection_ready(self, sender: Any, connection: Any, **kwargs: Any) -> None:
        if self._interrupted_jobs_marked:
            return
        self._interrupted_jobs_marked = True
        try:
            self._mark_interrupted_jobs()
        except (OperationalError, ProgrammingError):  # Database might be unavailable during migrations
            logging.getLogger(__name__).debug("Skipping interrupted job recovery; database not ready.")

    def _mark_interrupted_jobs(self) -> None:
        ExtractionJob = self.get_model('ExtractionJob')
        if ExtractionJob is None:
            return

        now = timezone.now()
        interrupted_count = ExtractionJob.objects.filter(status=ExtractionJob.Status.RUNNING).update(
            status=ExtractionJob.Status.ERROR,
            error='Job interrupted before completion. The extraction service was restarted.',
            finished_at=now,
            updated_at=now,
        )

        if interrupted_count:
            logging.getLogger(__name__).warning("Marked %s extraction job(s) as interrupted during startup.", interrupted_count)
