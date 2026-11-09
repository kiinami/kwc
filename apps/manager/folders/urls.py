from django.urls import path

from . import views

urlpatterns = [
    path("", views.folder_list, name="folder-list"),
    path("folders/new", views.folder_create, name="folder-create"),
    path("folders/search", views.folder_search, name="folder-search"),
    path("folders/<path:path>", views.folder_detail, name="folder-detail"),
]
