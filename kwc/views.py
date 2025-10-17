from __future__ import annotations

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView


class ManifestView(TemplateView):
    """Serve a dynamic web manifest so hashed static URLs stay accurate."""

    template_name = 'pwa/manifest.webmanifest'
    content_type = 'application/manifest+json'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        build_absolute = request.build_absolute_uri

        context.update(
            {
                'name': settings.PWA_APP_NAME,
                'short_name': settings.PWA_APP_SHORT_NAME,
                'description': settings.PWA_APP_DESCRIPTION,
                'start_url': build_absolute(settings.PWA_START_URL),
                'scope': build_absolute(settings.PWA_SCOPE),
                'display': settings.PWA_DISPLAY,
                'orientation': settings.PWA_ORIENTATION,
                'theme_color': settings.PWA_THEME_COLOR,
                'background_color': settings.PWA_BACKGROUND_COLOR,
                'lang': settings.LANGUAGE_CODE,
                'icon_sources': [
                    {
                        'src': build_absolute(static('kwc/icon.png')),
                        'sizes': '192x192',
                        'type': 'image/png',
                        'purpose': 'any maskable',
                    },
                    {
                        'src': build_absolute(static('kwc/icon.png')),
                        'sizes': '512x512',
                        'type': 'image/png',
                        'purpose': 'any maskable',
                    },
                ],
                'shortcuts': [
                    {
                        'name': 'Extract frames',
                        'short_name': 'Extract',
                        'description': 'Start a new extraction job',
                        'url': build_absolute(reverse('extract:index')),
                    },
                    {
                        'name': 'Choose wallpapers',
                        'short_name': 'Choose',
                        'description': 'Review and keep your favorite frames',
                        'url': build_absolute(reverse('choose:index')),
                    },
                    {
                        'name': 'Gallery',
                        'short_name': 'Gallery',
                        'description': 'Browse your wallpaper collection',
                        'url': build_absolute(reverse('gallery:index')),
                    },
                ],
            }
        )
        return context

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response['Cache-Control'] = 'no-cache'
        return response


@method_decorator(never_cache, name='dispatch')
class ServiceWorkerView(TemplateView):
    """Serve the service worker at the root scope."""

    template_name = 'pwa/service-worker.js'
    content_type = 'application/javascript'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        asset_urls = [
            reverse('gallery:index'),
            reverse('offline'),
            reverse('extract:index'),
            reverse('choose:index'),
            static('kwc/icon.png'),
            static('kwc/favicon.ico'),
        ]

        context.update(
            {
                'cache_name': settings.PWA_CACHE_ID,
                'asset_urls': asset_urls,
                'offline_url': reverse('offline'),
            }
        )
        return context

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response['Service-Worker-Allowed'] = '/'
        return response
