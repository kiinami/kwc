from django.urls import path

from . import views

urlpatterns = [
    path("importer", views.importer_index, name="importer-index"),
]
