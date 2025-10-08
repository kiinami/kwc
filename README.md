# KWC

KWC is a tiny Django app to extract keyframes from videos and curate them into a clean wallpaper set.

Apps:
- Extract: cut/trim and extract I-frame images using FFmpeg
- Choose: review images and quickly mark keep/delete, then apply and rename

## Configuration

Copy `.env.example` to `.env` and tweak as needed. Key variables:
- DJANGO_SECRET_KEY, DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS
- KWC_WALLPAPERS_FOLDER: where extracted images are stored (and served at /wallpapers/)
- KWC_FOLDER_PATTERN: folder naming template (Django template syntax)
- KWC_IMAGE_PATTERN: image filename template (supports the `pad` filter)

Defaults place a SQLite database in `/data` (bind mount recommended) and serve static files with WhiteNoise.

## Run (Docker)

Build and run the container exposing port 8080. Volumes mount the DB, static files, and wallpapers root.

- Image builds use uv and install only prod dependencies.
- Entrypoint `deploy/run` migrates the DB and starts Gunicorn (`prod`) or Django dev server (`serve`).

## Development

Install Python 3.13 and dependencies with your preferred manager. Example using uv:

1) Create a virtualenv and sync deps
2) Run the dev server

The navigation offers Home, Extract, and Choose. Wallpapers are also available under `/wallpapers/<folder>/<file>` for convenience.

## Notes

- No tests are provided by design for this refactor.
- Backwards-compatibility shims were intentionally removed. Templates use Django syntax only.