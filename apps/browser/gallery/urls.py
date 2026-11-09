from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="gallery-index"),
    path("browse/<path:path>", views.folder, name="gallery-folder"),
    path("i/<path:path>", views.original, name="gallery-original"),
    path("takedown", views.takedown, name="gallery-takedown"),
]
