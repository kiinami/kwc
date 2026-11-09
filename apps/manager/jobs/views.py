from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Job

_ACTIVE = {Job.Status.QUEUED, Job.Status.RUNNING, Job.Status.CANCELLING}


def job_list(request):
    status = request.GET.get("status", "")
    jobs = Job.objects.all()
    if status in Job.Status.values:
        jobs = jobs.filter(status=status)
    else:
        status = ""
    return render(
        request,
        "jobs/list.html",
        {
            "jobs": jobs,
            "active": jobs.filter(status__in=_ACTIVE).exists(),
            "status": status,
            "statuses": Job.Status.choices,
        },
    )


def job_detail(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    return render(request, "jobs/detail.html", {"job": job, "active": job.is_active})


@require_POST
def job_cancel(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if job.status == Job.Status.QUEUED:
        job.status = Job.Status.CANCELLED
        job.finished_at = timezone.now()
        job.message = "cancelled before start"
        job.save(update_fields=["status", "finished_at", "message"])
    elif job.status == Job.Status.RUNNING:
        job.cancel_requested = True
        job.status = Job.Status.CANCELLING
        job.save(update_fields=["cancel_requested", "status"])
    elif job.status == Job.Status.CANCELLING:
        job.cancel_requested = True
        job.save(update_fields=["cancel_requested"])
    return redirect("job-detail", job_id=job.id)
