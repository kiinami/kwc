"""
URL configuration for kwc project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve as static_serve

from choose import views as choose_views
from kwc import views as core_views

urlpatterns = [
    path('', core_views.HomeView.as_view(), name='home'),
    path('admin/', admin.site.urls),
    path('choose/', include(('choose.urls', 'choose'), namespace='choose')),
    path('extract/', include(('extract.urls', 'extract'), namespace='extract')),
    path('wall-thumbs/<str:folder>/<path:filename>', choose_views.thumbnail, name='wallpaper-thumbnail'),
    path('offline/', TemplateView.as_view(template_name='offline.html'), name='offline'),
    path('manifest.webmanifest', core_views.ManifestView.as_view(), name='pwa-manifest'),
    path('service-worker.js', core_views.ServiceWorkerView.as_view(), name='service-worker'),
]

# Serve wallpaper images directly from disk. This is intended for internal/self-hosted use.
_wall_root = getattr(settings, 'WALLPAPERS_FOLDER', None)
if _wall_root:
    urlpatterns += [
        re_path(r'^wallpapers/(?P<path>.+)$', static_serve, { 'document_root': _wall_root }),
    ]
