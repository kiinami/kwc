from django.urls import path

from . import views

app_name = "extract"

urlpatterns = [
    path("", views.index, name="index"),
    path("start/", views.start, name="start"),
    path("job/<str:job_id>/", views.job, name="job"),
    path("job/<str:job_id>/api/", views.job_api, name="job_api"),
    path("job/<str:job_id>/cancel/", views.cancel_job, name="cancel_job"),
    path("jobs/api/", views.jobs_api, name="jobs_api"),
    path("browse/api/", views.browse_api, name="browse_api"),
    path("guess/api/", views.guess_api, name="guess_api"),
    path("folders/api/", views.folders_api, name="folders_api"),
    path("tmdb/search/api/", views.tmdb_search_api, name="tmdb_search_api"),
    path("tmdb/posters/api/", views.tmdb_posters_api, name="tmdb_posters_api"),
]
