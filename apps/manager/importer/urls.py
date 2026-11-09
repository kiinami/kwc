from django.urls import path

from . import views

urlpatterns = [
    path("importer", views.importer_index, name="importer-index"),
    path("importer/browse", views.importer_browse, name="importer-browse"),
    path("importer/run", views.importer_run, name="importer-run"),
]
