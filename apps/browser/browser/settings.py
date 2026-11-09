"""Django settings for the public browser app."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Locally BASE_DIR is <repo>/apps/<app>; in the container it is flattened to /app.
REPO_ROOT = BASE_DIR.parent.parent
load_dotenv(REPO_ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-browser-dev-only"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

WALLPAPER_ROOT = Path(os.environ.get("KWC_WALLPAPER_ROOT", REPO_ROOT / "data" / "wallpapers"))
KWC_BROWSER_CACHE_ROOT = Path(os.environ.get("KWC_BROWSER_CACHE_ROOT", REPO_ROOT / "data" / "browser-cache"))
KWC_BROWSER_CACHE_MAX_BYTES = int(os.environ.get("KWC_BROWSER_CACHE_MAX_BYTES", str(5 * 1024**3)))
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", BASE_DIR / "staticfiles"))

# The browser is deliberately stateless: it only reads the wallpaper folder.
# No auth, admin, sessions, or database apps are installed.
INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "gallery",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "browser.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "browser.wsgi.application"

DATABASES = {}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

STORAGES = {
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_USE_FINDERS = DEBUG

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
