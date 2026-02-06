from django.urls import path

from . import views
from .views import save_api

app_name = 'choose'

urlpatterns = [
    path('', views.index, name='index'),
    path('inbox/', views.inbox, name='inbox'),
    path('inbox/<str:folder>/gallery/', views.inbox_gallery, name='inbox_gallery'),
    path('inbox/<str:folder>/delete', views.delete_folder, name='inbox_delete'),
    path('inbox/<str:folder>/lightbox/<str:filename>', views.inbox_lightbox, name='inbox_lightbox'),
    path('inbox/<str:folder>/', views.inbox_folder, name='inbox_folder'),
    path('inbox/<str:folder>/decide', views.decide_api, name='inbox_decide'),
    path('inbox/<str:folder>/save', save_api, name='inbox_save_api'),
    path('<str:folder>/gallery/', views.gallery, name='gallery'),
    path('<str:folder>/lightbox/<str:filename>', views.lightbox, name='lightbox'),
    path('<str:folder>/', views.folder, name='folder'),
    path('<str:folder>/decide', views.decide_api, name='decide'),
    path('<str:folder>/save', save_api, name='save_api'),
]
