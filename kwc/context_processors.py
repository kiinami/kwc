from __future__ import annotations

from django.conf import settings


def pwa(request):
    """Expose PWA-related settings in templates."""

    return {
        "PWA": {
            "theme_color": settings.PWA_THEME_COLOR,
            "background_color": settings.PWA_BACKGROUND_COLOR,
            "app_name": settings.PWA_APP_NAME,
            "short_name": settings.PWA_APP_SHORT_NAME,
        }
    }
