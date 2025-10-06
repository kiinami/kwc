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
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('admin/', admin.site.urls),
    path('choose/', include(('choose.urls', 'choose'), namespace='choose')),
    path('extract/', include(('extract.urls', 'extract'), namespace='extract')),
]

# In development, serve wallpaper images directly from disk for previews
if settings.DEBUG:
    urlpatterns += static('/wallpapers/', document_root=getattr(settings, 'WALLPAPERS_FOLDER', getattr(settings, 'EXTRACT_DEFAULT_ROOT', None)))
