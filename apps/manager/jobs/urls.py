from django.urls import path

from . import views

urlpatterns = [
    path("jobs", views.job_list, name="job-list"),
    path("jobs/<uuid:job_id>", views.job_detail, name="job-detail"),
    path("jobs/<uuid:job_id>/cancel", views.job_cancel, name="job-cancel"),
]
