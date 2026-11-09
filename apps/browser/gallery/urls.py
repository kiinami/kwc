from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="gallery-index"),
    path("browse/<path:path>", views.folder, name="gallery-folder"),
    path("view/<path:path>", views.lens, name="gallery-lens"),
    path("i/<path:path>", views.original, name="gallery-original"),
    path("t/<path:path>", views.thumb, name="gallery-thumb"),
    path("l/<path:path>", views.lens_image, name="gallery-lens-image"),
    path("downloads.json", views.downloads_json, name="gallery-downloads"),
    path("takedown", views.takedown, name="gallery-takedown"),
]
