from django.urls import path

from . import views

app_name = 'gallery'

urlpatterns = [
    path('', views.index, name='index'),
    path('<str:folder>/', views.gallery, name='gallery'),
    path('<str:folder>/lightbox/<str:filename>', views.lightbox, name='lightbox'),
]
