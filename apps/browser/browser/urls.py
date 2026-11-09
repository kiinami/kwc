"""URL configuration for the browser app."""

from django.urls import include, path

urlpatterns = [
    path("", include("gallery.urls")),
]
