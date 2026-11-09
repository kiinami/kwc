from django.urls import path

from . import views

urlpatterns = [
    path("importer", views.importer_index, name="importer-index"),
    path("importer/run", views.importer_run, name="importer-run"),
]
