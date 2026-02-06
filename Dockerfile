# Multi-stage, uv-driven production image for Django (kwc)

### BUILD IMAGE ###
FROM python:3.13-slim AS builder

ENV DJANGO_SETTINGS_MODULE=kwc.settings \
    PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/root/.cache/uv \
    UV_COMPILE_BYTECODE=1 \
    UV_FROZEN=1 \
    UV_LINK_MODE=copy \
    UV_NO_MANAGED_PYTHON=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_REQUIRE_HASHES=1 \
    UV_VERIFY_HASHES=1 \
    VIRTUAL_ENV=/venv

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:0.4.29 /uv /usr/local/bin/uv

# System deps for building wheels if needed
RUN <<EOT
set -eu
apt-get update -y && \
apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*
EOT

WORKDIR /app

# Install prod deps into a venv based on lockfile
RUN --mount=type=cache,target=/app/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock,readonly=false \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv venv $VIRTUAL_ENV && \
    uv sync --frozen --no-install-project --no-editable

# Copy only what's needed for Django management/collectstatic
COPY kwc /app/kwc
COPY choose /app/choose
COPY extract /app/extract
COPY recommend /app/recommend
COPY templates /app/templates
COPY manage.py /app/


### FINAL IMAGE ###
FROM python:3.13-slim

ARG PORT=8000
ENV DJANGO_SETTINGS_MODULE=kwc.settings \
    PATH="/venv/bin:$PATH" \
    PORT=${PORT} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/venv

EXPOSE ${PORT}
WORKDIR /app

ENTRYPOINT ["/bin/bash", "/app/deploy/run"]
CMD ["prod"]

# Minimal OS deps for runtime
RUN <<EOT
set -eu
apt-get clean -y && \
apt-get update -y && \
apt-get install -y --no-install-recommends \
    bash \
    ffmpeg \
    ca-certificates \
    && apt-get autoremove -y && \
    apt-get clean -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

# Copy selectively from builder to optimize final image.
COPY --link --from=builder /venv /venv
COPY --link --from=builder /app/kwc /app/kwc
COPY --link --from=builder /app/choose /app/choose
COPY --link --from=builder /app/extract /app/extract
COPY --link --from=builder /app/recommend /app/recommend
COPY --link --from=builder /app/templates /app/templates
COPY --link --from=builder /app/manage.py /app/manage.py

# Add runtime scripts
COPY deploy /app/deploy
RUN chmod +x /app/deploy/run
