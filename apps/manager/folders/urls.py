from django.urls import path

from . import views

urlpatterns = [
    path("", views.folder_list, name="folder-list"),
    path("folders/new", views.folder_create, name="folder-create"),
    path("folders/search", views.folder_search, name="folder-search"),
    path("folders/<path:path>/hide", views.folder_hide, name="folder-hide"),
    path("folders/<path:path>/cover", views.folder_cover, name="folder-cover"),
    path("folders/<path:path>/rename", views.folder_rename, name="folder-rename"),
    path("folders/<path:path>/delete", views.folder_delete, name="folder-delete"),
    path("folders/<path:path>", views.folder_detail, name="folder-detail"),
]
