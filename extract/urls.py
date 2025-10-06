from django.urls import path
from . import views

app_name = 'extract'

urlpatterns = [
    path('', views.index, name='index'),
    path('start/', views.start, name='start'),
    path('job/<str:job_id>/', views.job, name='job'),
    path('job/<str:job_id>/api/', views.job_api, name='job_api'),
    path('jobs/api/', views.jobs_api, name='jobs_api'),
    path('browse/api/', views.browse_api, name='browse_api'),
    path('browse/mkdir/', views.browse_mkdir_api, name='browse_mkdir_api'),
    path('guess/api/', views.guess_api, name='guess_api'),
]
