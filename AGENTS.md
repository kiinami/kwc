# Copilot Agent Instructions for KWC

## Overview

**KWC**: Django 5.2.7 app for extracting video keyframes (FFmpeg), deduplicating them (CNN-based), and curating wallpapers. Two apps: **Extract** (video→images) and **Choose** (review/rename). Python 3.13 only, Docker deployment.

## Project Structure

**Key directories:**
- `kwc/` - Django project: settings.py (env config), urls.py, wsgi.py, context_processors.py (PWA), static/
- `choose/` - App: models.py (ImageDecision, FolderProgress), views.py, api.py (JSON endpoints), services.py, tests/
- `extract/` - App: models.py (ExtractionJob), extractor.py (FFmpeg), deduplication.py (CNN/imagededup), tmdb.py (metadata), job_runner.py, forms.py, tests/
- `templates/` - Project templates (base.html, home.html, offline.html)
- `deploy/run` - Docker entrypoint (migrations, gunicorn/dev server)

**Config files:**
- `pyproject.toml` - Dependencies: `django`, `python-ffmpeg`, `imagededup`, `tensorflow`, `tmdbsimple`. Tool configs: `ruff`, `pytest`, `mypy`.
- `.editorconfig` - 4 spaces (Python), 2 spaces (YAML/JS), tabs (HTML templates)
- `.python-version` - `3.13`
- `uv.lock` - Committed lockfile
- `Dockerfile` - Multi-stage (uv 0.4.29)

**Django settings (kwc/settings.py)** - All env-configurable:
- `DJANGO_*`: SECRET_KEY, DEBUG, ALLOWED_HOSTS
- `KWC_WALLPAPERS_FOLDER`: Image storage (default: ./extracted)
- `KWC_FOLDER_PATTERN` / `KWC_IMAGE_PATTERN`: Django template syntax
- `KWC_EXTRACT_WORKERS`: FFmpeg parallelism (default: CPU count)
- `KWC_PWA_*`: App name, theme color, etc
- Uses SQLite (root dir, `/data` in Docker), WhiteNoise static files, pure Django templates (no Jinja2)

**GitHub Workflows:**
- `.github/workflows/copilot-setup-steps.yml` - Common setup steps (Python env, uv sync, .env, migrations)
- `.github/workflows/publish.yml` - Docker build→GHCR (30min timeout, no linting/tests in CI)
- `.github/workflows/test.yml` - Test workflow (uv sync, pytest)
- `.github/workflows/ruff.yml` - Ruff linter workflow
- `.github/workflows/mypy.yml` - Mypy type checking workflow

## Environment Setup

**Python 3.13 required** (lockfile pinned). The environment is automatically set up by the workflow at `.github/workflows/copilot-setup-steps.yml` before you start working. This includes:
- Installing uv and dependencies (`uv sync`)
- Creating `.env` from `.env.example`
- Running database migrations

Key .env variables: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `KWC_WALLPAPERS_FOLDER` (default: ./extracted)

## Development Workflow

**Dev server**: `uv run manage.py runserver` → http://127.0.0.1:8000/  
**Tests**: `uv run pytest -v` → comprehensive tests pass (~1-2s), warnings normal (missing /static/)  
**Static files**: `uv run manage.py collectstatic --noinput` (WhiteNoise compression)
**Docker**: `docker build -t kwc-web .` (~2-3min), `docker-compose up` (port 8080)

**Agent Contribution Workflow**:
1. **Start**: Always create a new branch `git checkout -b <branch-name>` (e.g., `feat/...` or `fix/...`).
2. **Work**: Commit atomically as you progress.
3. **Verify Locally**: Run full repository checks before pushing:
   - Format: `uv run ruff format .`
   - Lint: `uv run ruff check .`
   - Type check: `uv run mypy .`
   - Test: `uv run pytest`
4. **Finish**: Push to origin and create a PR to `main`.
5. **Verify CI**: Check PR checks (CI). If they fail, get results and fix the issues until green.

## Key Patterns & Guidelines

**Testing**: Despite README saying "No tests by design", there ARE comprehensive tests. Always run `uv run python -m pytest -v` before/after changes (fast, ~1-2s).

**Templates**: Pure Django syntax (no Jinja2). Custom filters in `extract/templatetags/` (e.g., `pad` for zero-padding).

**APIs**: Manual JSON parsing in `choose/api.py` (not DRF), CSRF via headers.

**Jobs**: Foreground execution (no Celery), `job_runner.py` uses process pooling. Phases: Extraction (FFmpeg) -> Deduplication (MobileNet/CNN).

**Deduplication**: Uses `imagededup` with logic in `extract/deduplication.py`. Handles similarity thresholds.

**PWA**: Dynamic manifest/service worker via `kwc/context_processors.py`, pre-caches `/`, `/extract/`, `/choose/`, `/offline/`.

**File changes:**
- New app: Add to `kwc/settings.py` INSTALLED_APPS
- Static files: `kwc/static/` → `uv run manage.py collectstatic`
- URLs: Root in `kwc/urls.py`, app-specific in `{app}/urls.py`
- Dependencies: Edit `pyproject.toml` → `uv lock && uv sync`

**Critical rules:**
1. **Never modify TODO.md**
2. **Never edit .env or any environment variable files** - Only the user may change them
3. **No backwards compatibility** - No need to keep any shims, or support methods that are not used. Just make sure that they are not used anywhere, and delete them.
4. **Trust these instructions** - Only search if info incomplete/incorrect
5. FFmpeg not needed for tests (mocked)
6. Docker Compose: non-root user via `KWC_UID`/`KWC_GID` env vars

**Git:**
- You can commit as you work
- Write clear, concise commit messages summarizing changes
- Use Conventional Commits style when possible (e.g., feat:, fix:, docs:, chore:)
- In Conventional Commits, add scope if relevant (e.g., feat(extract): ...)
- Revert files only when the change is yours or explicitly requested
- Always double-check git status before any commit
- Keep commits atomic: commit only the files you touched and list each path explicitly

**Code Formatting and Linting:**

1. Pre-commit
   - Config: `.pre-commit-config.yaml`
   - Runs: on git commit

2. Ruff
   - Format: `uv run ruff format .`
   - Check: `uv run ruff check .`
   - Fix: `uv run ruff check . --fix`
   - Will run automatically when committing after pre-commit is set up

3. Typing
   - Check: `uv run mypy .`
   - Fix typing issues before committing
   - Will run automatically when committing after pre-commit is set up

**File operations:**
- Delete unused or obsolete files when your changes make them irrelevant (refactors, feature removals, etc.)
- Moving/renaming and restoring files is allowed

**Django 5.2.7**: Check https://docs.djangoproject.com/en/5.2/ for API references.
