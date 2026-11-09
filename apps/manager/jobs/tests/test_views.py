import pytest

from jobs.models import Job


@pytest.mark.django_db
def test_job_list_shows_status_and_progress(auth_client):
    Job.objects.create(
        kind="importer.run",
        status=Job.Status.RUNNING,
        progress_current=2,
        progress_total=5,
        message="imported 2/5",
    )
    response = auth_client.get("/jobs")
    assert response.status_code == 200
    assert b"importer.run" in response.content
    assert b"running" in response.content.lower()
    assert b"2 / 5" in response.content


@pytest.mark.django_db
def test_job_detail_shows_error(auth_client):
    job = Job.objects.create(kind="extract", status=Job.Status.ERROR, error="traceback here")
    response = auth_client.get(f"/jobs/{job.id}")
    assert response.status_code == 200
    assert b"traceback here" in response.content
    assert b"extract" in response.content


@pytest.mark.django_db
def test_cancel_queued_job(auth_client):
    job = Job.objects.create(kind="importer.run", status=Job.Status.QUEUED)
    response = auth_client.post(f"/jobs/{job.id}/cancel")
    assert response.status_code == 302
    job.refresh_from_db()
    assert job.status == Job.Status.CANCELLED


@pytest.mark.django_db
def test_cancel_running_job_requests_cooperative_cancel(auth_client):
    job = Job.objects.create(kind="extract", status=Job.Status.RUNNING)
    auth_client.post(f"/jobs/{job.id}/cancel")
    job.refresh_from_db()
    assert job.status == Job.Status.CANCELLING
    assert job.cancel_requested is True


@pytest.mark.django_db
def test_jobs_require_login(client):
    response = client.get("/jobs")
    assert response.status_code == 302
