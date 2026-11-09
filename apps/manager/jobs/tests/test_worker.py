import pytest

from jobs.models import Job, enqueue
from jobs.registry import register
from jobs.worker import run_worker


@pytest.mark.django_db
def test_handler_completes_and_reports_progress():
    @register("test.ok")
    def handler(job, ctx):
        ctx.progress(1, total=2, message="halfway")
        return {"done": True}

    job = enqueue("test.ok", {})
    run_worker(once=True)
    job.refresh_from_db()
    assert (job.status, job.progress_current, job.result) == ("done", 1, {"done": True})
    assert job.progress_total == 2
    assert job.started_at is not None
    assert job.finished_at is not None


@pytest.mark.django_db
def test_exception_marks_error():
    @register("test.fail")
    def handler(job, ctx):
        raise RuntimeError("boom")

    enqueue("test.fail", {})
    run_worker(once=True)
    job = Job.objects.get()
    assert job.status == "error"
    assert "boom" in job.error


@pytest.mark.django_db
def test_unknown_handler_marks_error():
    enqueue("test.missing", {})
    run_worker(once=True)
    job = Job.objects.get()
    assert job.status == "error"
    assert "no handler" in job.error


@pytest.mark.django_db
def test_cancellation_is_cooperative():
    @register("test.cancel")
    def handler(job, ctx):
        ctx.check_cancelled()

    job = Job.objects.create(kind="test.cancel", cancel_requested=True)
    run_worker(once=True)
    job.refresh_from_db()
    assert job.status == "cancelled"


@pytest.mark.django_db
def test_worker_interrupts_stale_running_jobs():
    Job.objects.create(kind="x", status="running")
    run_worker(once=True)
    assert Job.objects.get().status == "interrupted"


@pytest.mark.django_db
def test_progress_writes_are_debounced():
    @register("test.slow")
    def handler(job, ctx):
        ctx.progress(1, total=10)
        ctx.progress(2, total=10)
        return {}

    enqueue("test.slow", {})
    run_worker(once=True)
    assert Job.objects.get().progress_current == 2
