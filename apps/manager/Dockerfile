# syntax=docker/dockerfile:1

FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_FROZEN=1

WORKDIR /app

# Workspace metadata is needed to resolve the lockfile.
COPY pyproject.toml uv.lock ./
COPY apps/browser/pyproject.toml apps/browser/pyproject.toml
COPY apps/manager/pyproject.toml apps/manager/pyproject.toml
COPY libs ./libs

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package manager --no-install-project

COPY apps/manager ./apps/manager

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package manager --no-editable && \
    DJANGO_SECRET_KEY=build-only \
    DJANGO_DEBUG=false \
    DJANGO_DB_PATH=/tmp/db.sqlite3 \
    KWC_WALLPAPER_ROOT=/tmp/wallpapers \
    /venv/bin/python apps/manager/manage.py collectstatic --noinput

FROM python:3.14-slim AS runtime

ENV DJANGO_SETTINGS_MODULE=manager.settings \
    HOME=/tmp \
    PATH="/venv/bin:$PATH" \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/venv

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

COPY --from=builder /venv /venv
COPY --from=builder /app/apps/manager /app

RUN chmod +x /app/entrypoint.sh && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
