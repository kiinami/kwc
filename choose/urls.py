from django.urls import path

from . import views
from .views import save_api

app_name = 'choose'

urlpatterns = [
    path('', views.index, name='index'),
    path('<str:folder>/', views.folder, name='folder'),
    path('<str:folder>/decide', views.decide_api, name='decide'),
    path('<str:folder>/save', save_api, name='save_api'),
]
