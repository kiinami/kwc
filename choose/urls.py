from django.urls import path
from . import views

app_name = 'choose'

urlpatterns = [
    path('', views.index, name='index'),
    path('<str:folder>/', views.folder, name='folder'),
    path('<str:folder>/decide', views.decide_api, name='decide'),
    path('<str:folder>/save', views.save_api, name='save_api'),
]
