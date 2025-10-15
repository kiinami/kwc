# KWC

KWC is a tiny Django app to extract keyframes from videos and curate them into a clean wallpaper set.

Apps:
- Extract: cut/trim and extract I-frame images using FFmpeg
- Choose: review images and quickly mark keep/delete, then apply and rename

## Prerequisites

- Python 3.13 (matches the runtime in the Docker image and lockfile)
- [uv 0.4.29](https://github.com/astral-sh/uv) for dependency and virtualenv management
- Docker 24+ (optional, only for container workflows)

Guides for setup and workflow will live in [Contributing](#contributing) and [Testing](#testing) soon.

## Configuration

Copy `.env.example` to `.env` and tweak as needed. Key variables:
- DJANGO_SECRET_KEY, DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS
- KWC_WALLPAPERS_FOLDER: where extracted images are stored (and served at /wallpapers/)
- KWC_FOLDER_PATTERN: folder naming template (Django template syntax)
- KWC_IMAGE_PATTERN: image filename template (supports the `pad` filter)
- KWC_EXTRACT_WORKERS: override the number of parallel FFmpeg workers (default: CPU count)
- KWC_FILE_PICKER_START_PATH: default start path for the file picker in extract form (default: /)

Defaults place a SQLite database in `/data` (bind mount recommended) and serve static files with WhiteNoise.

## Run (Docker)

Build and run the container exposing port 8080. Volumes mount the DB, static files, and wallpapers root.

- Image builds use uv and install only prod dependencies.
- Entrypoint `deploy/run` migrates the DB and starts Gunicorn (`prod`) or Django dev server (`serve`).

## Development

Install Python 3.13 and dependencies with your preferred manager. Example using uv 0.4.29:

1) Create a virtualenv and sync deps
2) Run the dev server

The navigation offers Home, Extract, and Choose. Wallpapers are also available under `/wallpapers/<folder>/<file>` for convenience.

## Progressive Web App

The UI now ships with a full PWA experience:

- `manifest.webmanifest` and a root-scoped service worker are generated dynamically so hashed static assets stay fresh.
- Core screens (`/`, `/extract/`, `/choose/`) plus the offline fallback are pre-cached for quick launches.
- When offline, navigation gracefully falls back to `/offline/` with options to retry or continue browsing cached data.
- Users on supported devices see an “Install app” button in the header once the browser is ready for installation.

You can tweak key parameters through environment variables:

| Setting | Env var | Default |
| --- | --- | --- |
| `PWA_APP_NAME` | `KWC_PWA_APP_NAME` | `KWC Wallpapers` |
| `PWA_APP_SHORT_NAME` | `KWC_PWA_SHORT_NAME` | `KWC` |
| `PWA_THEME_COLOR` | `KWC_PWA_THEME_COLOR` | `#0b1020` |
| `PWA_BACKGROUND_COLOR` | `KWC_PWA_BACKGROUND_COLOR` | `#0b1020` |
| `PWA_START_URL` | `KWC_PWA_START_URL` | `/` |
| `PWA_CACHE_ID` | `KWC_PWA_CACHE_ID` | `kwc-pwa-v1` |

After changing cache-related settings, deployers should bump `KWC_PWA_CACHE_ID` so clients fetch the new service worker urgently.

## Notes

- No tests are provided by design for this refactor.
- Backwards-compatibility shims were intentionally removed. Templates use Django syntax only.

## Contributing

Details coming soon — track workflow updates here.

## Testing

Planned instructions will land here alongside the Contributing guide.