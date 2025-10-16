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

Defaults place a SQLite database in `/data` (bind mount recommended) and serve static files with WhiteNoise.

### TMDB Cover Art Integration

KWC optionally integrates with [The Movie Database (TMDB)](https://www.themoviedb.org/) to allow you to select professional poster art as folder cover images during extraction. To enable this feature:

1. Create a free account at [https://www.themoviedb.org/](https://www.themoviedb.org/)
2. Get your API key from [https://www.themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)
3. Add it to your `.env` file:
   ```
   TMDB_API_KEY=your_api_key_here
   ```

When configured, the extract form will include a cover image field where you can search for and select poster art. The selected image will be downloaded and saved as `.cover.jpg` in the extraction folder. If a folder already has a cover image, the field will display it as read-only.

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

## Testing

The project includes comprehensive tests covering the core functionality. Run tests with:

```bash
python -m pytest -v
```

Tests cover:
- Extract app: video extraction, job management, TMDB integration, file browsing
- Choose app: image curation, folder management, renaming logic
- 79 tests in total, all passing

## Contributing

Details coming soon — track workflow updates here.

## Notes

- Backwards-compatibility shims were intentionally removed. Templates use Django syntax only.