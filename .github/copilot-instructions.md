# Copilot Agent Instructions for KWC

## Repository Overview

**KWC** is a tiny Django 5.2.7 web application for extracting keyframes from videos and curating them into wallpaper sets. It consists of two main apps:
- **Extract**: Cut/trim and extract I-frame images using FFmpeg
- **Choose**: Review images and quickly mark keep/delete, then apply and rename

**Size**: Small codebase (~20 Python files, 2 Django apps)
**Languages/Frameworks**: Python 3.13, Django 5.2.7, HTML/JavaScript templates
**Key Dependencies**: FFmpeg, uv 0.4.29, Gunicorn, WhiteNoise, Pillow
**Runtime**: Python 3.13 (strict version requirement)
**Deployment**: Docker containers with multi-stage builds

## Build and Test Instructions

### Prerequisites

**CRITICAL**: This project requires Python 3.13 exactly (not 3.12 or earlier). The lockfile and Docker image are pinned to 3.13.
- Python 3.13
- uv 0.4.29 for dependency management
- FFmpeg (runtime dependency for video processing)
- Docker 24+ (optional, for container workflows)

### Environment Setup

**Always follow this order:**

1. Install uv if not available:
   ```bash
   pip install uv==0.4.29
   ```

2. Create virtualenv and sync dependencies (takes ~10-15 seconds):
   ```bash
   uv venv
   uv sync --group prod
   ```
   **IMPORTANT**: Always run `uv sync --group prod` to install both base and prod dependencies (whitenoise, gunicorn). Tests fail without prod dependencies even though they're in a separate dependency group.

3. Copy environment configuration:
   ```bash
   cp .env.example .env
   ```
   The .env file is required for Django settings. Key variables:
   - `DJANGO_SECRET_KEY`: Required, change from default
   - `DJANGO_DEBUG`: Set to True for development
   - `DJANGO_ALLOWED_HOSTS`: Defaults to `*` for local dev
   - `KWC_WALLPAPERS_FOLDER`: Where extracted images are stored (default: `./extracted`)

4. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```

### Database Migrations

**Always run migrations before starting the dev server or running tests:**
```bash
python manage.py migrate
```

This creates the SQLite database at the project root (default: `db.sqlite3`, gitignored).

### Running the Development Server

```bash
python manage.py runserver
```

The server starts on http://127.0.0.1:8000/ with routes:
- `/` - Home page listing media folders
- `/extract/` - Video extraction interface
- `/choose/` - Image curation interface
- `/wallpapers/<folder>/<file>` - Direct media access

### Running Tests

**Command:**
```bash
python -m pytest -v
```

**Expected**: All 36 tests pass in ~1 second. 8 warnings about missing static directory are normal (collectstatic not run in test mode).

**Common Issues:**
- If tests fail with `ModuleNotFoundError: No module named 'whitenoise'`, you need to run `uv sync --group prod` to install production dependencies.
- Tests use temporary directories and mocking; no FFmpeg required.

### Building Static Assets

```bash
python manage.py collectstatic --noinput
```

Collects static files from `kwc/static/` to `./static/` (default). Uses WhiteNoise's `CompressedManifestStaticFilesStorage` for long-lived caching.

### Docker Build

**Build time**: ~2-3 minutes for multi-stage build

```bash
docker build -t kwc-web:latest .
```

The Dockerfile uses:
- Python 3.13-slim base
- uv 0.4.29 from official image
- Multi-stage build (builder + final)
- Production dependencies only (`uv sync --group prod --frozen`)
- FFmpeg installed in final image

**Run container:**
```bash
docker-compose up
```

Exposes port 8080, mounts volumes for data persistence.

## Project Architecture

### Directory Structure

```
kwc/
├── .github/
│   └── workflows/publish.yml    # Docker image build/push to GHCR (30min timeout)
├── kwc/                          # Main Django project
│   ├── settings.py              # Django settings, env var configuration
│   ├── urls.py                  # Root URL configuration
│   ├── wsgi.py                  # WSGI application entry point
│   ├── context_processors.py   # PWA context processor
│   ├── static/                  # Project-level static assets (favicons, etc)
│   └── utils/                   # Shared utilities
├── choose/                       # Image curation Django app
│   ├── models.py                # ImageDecision, FolderProgress models
│   ├── views.py                 # Gallery, thumbnail, save views
│   ├── api.py                   # Decision API endpoints
│   ├── services.py              # Business logic for folder/image management
│   ├── templates/choose/        # Choose app templates
│   └── tests/                   # Comprehensive tests (test_*.py)
├── extract/                      # Video extraction Django app
│   ├── models.py                # ExtractionJob model
│   ├── views.py                 # Extraction form and job views
│   ├── extractor.py             # FFmpeg wrapper for frame extraction
│   ├── job_runner.py            # Background job execution
│   ├── forms.py                 # Extraction form with validation
│   ├── templates/extract/       # Extract app templates
│   └── tests/                   # Unit tests for extractor/job_runner
├── templates/                    # Project-level templates (base.html, home.html)
├── deploy/
│   └── run                      # Entrypoint script for Docker (migrations, gunicorn, dev server)
├── manage.py                    # Django management script
├── pyproject.toml               # Project metadata, dependencies, pytest config
├── uv.lock                      # Locked dependencies (committed)
├── .env.example                 # Environment template
└── Dockerfile                   # Multi-stage production image
```

### Configuration Files

- **pyproject.toml**: Project dependencies split into base, dev, prod groups. Pytest configuration with Django settings module.
- **.editorconfig**: Code style (4 spaces Python, 2 spaces YAML/JS, tabs for HTML templates).
- **.gitignore**: Standard Python/Django ignores plus `data/`, `.env`, `media/`, `*.sqlite3`.
- **.python-version**: `3.13` (used by uv and pyenv).
- **docker-compose.yml**: Single service (`web`) with volume mounts for persistence.

### Django Settings (kwc/settings.py)

Key settings configurable via environment variables:
- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`
- `KWC_WALLPAPERS_FOLDER`: Extracted images root (default: `./extracted`)
- `KWC_FOLDER_PATTERN`: Django template syntax for folder naming
- `KWC_IMAGE_PATTERN`: Django template syntax for image filename (supports custom `pad` filter)
- `KWC_EXTRACT_WORKERS`: FFmpeg parallelism (default: CPU count)
- `KWC_PWA_*`: PWA manifest customization (app name, theme color, etc)

**Important**: The project uses:
- SQLite database (default: root directory, `/data` in Docker)
- WhiteNoise for static files (no separate CDN required)
- Django 5.2.7 template syntax throughout (no Jinja2)

### CI/CD Pipeline

**.github/workflows/publish.yml**:
- Triggers: Push to `main`, manual workflow dispatch
- Builds Docker image for `linux/amd64`
- Pushes to `ghcr.io/kiinami/kwc` with `latest` and SHA tags
- Uses GitHub Actions cache for BuildKit layers
- **Timeout**: 30 minutes (important for debugging)

**No linting or testing** in CI currently. Tests are run locally only.

## Code Change Guidelines

### Testing Strategy

**The README explicitly states**: "No tests are provided by design for this refactor."

However, the project **DOES have comprehensive tests** (36 tests across choose and extract apps). When making changes:
1. Always run `python -m pytest -v` before and after changes
2. Tests are fast (~1s) and cover views, API endpoints, services, and utilities
3. Expected: 36 passed, 8 warnings (missing static directory is normal)

### Known Issues and Workarounds

1. **Prod dependencies required for tests**: Even though tests are in the `dev` group, they import production middleware (WhiteNoise). Always run `uv sync --group prod`.

2. **Static directory warnings**: Tests produce warnings about missing `/static/` directory. This is expected behavior (collectstatic not run in test mode). Ignore these 8 warnings.

3. **Python version strictness**: The project requires Python 3.13. Using 3.12 or earlier may cause compatibility issues with dependencies in uv.lock.

4. **FFmpeg not required for tests**: All FFmpeg operations are mocked in tests. Only needed for actual video extraction in runtime.

### Common Development Patterns

**Django Templates**: The project uses pure Django template syntax (no Jinja2). Custom template filters defined in `extract/templatetags/` (e.g., `pad` filter for zero-padding).

**Environment Variables**: Extensive use of `os.getenv()` with sensible defaults. Settings helper functions: `_bool_env()`, `_int_setting()`, `_float_setting()`.

**API Endpoints**: JSON APIs in `choose/api.py` use manual JSON parsing (not DRF). CSRF protection via token in headers.

**Background Jobs**: Extraction jobs run in foreground (no Celery/RQ). Uses `job_runner.py` with process pooling for parallel FFmpeg workers.

### File Locations for Common Tasks

- **Add new Django app**: Create in project root, register in `kwc/settings.py` INSTALLED_APPS
- **Modify static files**: Place in `kwc/static/`, run `python manage.py collectstatic`
- **Change URL routes**: Root routes in `kwc/urls.py`, app routes in `{app}/urls.py`
- **Add dependencies**: Update `pyproject.toml` dependencies section, run `uv lock && uv sync --group prod`
- **Modify Docker entrypoint**: Edit `deploy/run` script
- **Update GitHub Actions**: Edit `.github/workflows/publish.yml`

### Progressive Web App (PWA)

The application includes full PWA support:
- `manifest.webmanifest` and service worker generated dynamically
- Pre-caches core screens (`/`, `/extract/`, `/choose/`) and offline fallback
- Configurable via `KWC_PWA_*` environment variables
- Context processor in `kwc/context_processors.py` provides PWA variables to templates

## Important Notes

1. **Trust these instructions**: The information here is validated against the actual codebase. Only search/explore if instructions are incomplete or proven incorrect.

2. **No backwards compatibility**: README states "Backwards-compatibility shims were intentionally removed." Don't add legacy support without discussion.

3. **TODO.md**: Contains future work. The first line states "For Copilot: DO NOT EDIT THIS FILE". Avoid modifying unless explicitly asked.

4. **Django version**: Uses Django 5.2.7 features. Check Django docs at https://docs.djangoproject.com/en/5.2/ for syntax/API questions.

5. **Container user management**: Docker Compose runs as non-root user (configurable via `KWC_UID`/`KWC_GID` env vars) to avoid permission issues with bind mounts.

6. **Database location**: Default SQLite at project root. In Docker, uses `/data` directory (should be a volume for persistence).

## Quick Reference Commands

```bash
# Full setup from scratch
pip install uv==0.4.29
uv venv
uv sync --group prod
cp .env.example .env
source .venv/bin/activate
python manage.py migrate

# Run dev server
python manage.py runserver

# Run tests
python -m pytest -v

# Build static assets
python manage.py collectstatic --noinput

# Docker build and run
docker build -t kwc-web:latest .
docker-compose up

# Add new dependency
# 1. Edit pyproject.toml [project.dependencies]
# 2. Run: uv lock && uv sync --group prod
```
