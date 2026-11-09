# kwc

A wallpaper collection split into two isolated Django apps that share one wallpaper folder:

- **browser** — public, read-only browser and downloader. It derives everything from the wallpaper folder and keeps no database.
- **manager** — writes and organizes the wallpaper folder. It will sit behind OIDC login and keeps its own SQLite database.

The two apps never talk to each other. The wallpaper folder is the contract between them.

## Repository layout

```
apps/browser/     public read-only browser
apps/manager/     wallpaper manager
libs/             shared workspace libraries (currently a placeholder)
data/wallpapers/  default host wallpaper folder
data/manager/     manager database volume
docker-compose.yml       production-style stack
docker-compose.dev.yml   local development stack with hot reload
```

## Prerequisites

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose (optional, for container work)

## Local development without Docker

```sh
cp .env.example .env
uv sync
uv run python apps/browser/manage.py runserver 0.0.0.0:8080
uv run python apps/manager/manage.py migrate
uv run python apps/manager/manage.py runserver 0.0.0.0:8081
# In another terminal: the durable manager worker
uv run python apps/manager/manage.py runworker
```

`.env.example` contains local-only development values (`DJANGO_DEBUG=true` and a throwaway secret). By default the apps read `data/wallpapers` from the repository root and the manager writes its database to `apps/manager/db.sqlite3`.

## Development with Docker

```sh
cp .env.example .env
docker compose -f docker-compose.dev.yml up
```

- Browser: <http://localhost:8080>
- Manager: <http://localhost:8081>

The dev stack bind-mounts the repository, so code changes reload automatically. The manager migrates its database on startup.

## Production-style stack

```sh
cp .env.example .env
# set BROWSER_SECRET_KEY and MANAGER_SECRET_KEY, e.g. openssl rand -hex 32
docker compose up -d --build
```

The compose file mounts the same host wallpaper folder twice:

- manager: read-write
- browser: read-only, with a read-only root filesystem and a tmpfs `/tmp`

The browser has no database volume. The manager keeps its database under `data/manager` by default. The manager binds to `127.0.0.1` by default until OIDC and a reverse proxy are in place; set `MANAGER_BIND=0.0.0.0` only when it sits behind that proxy. If your host user is not UID/GID 1000, set `KWC_UID` and `KWC_GID` to the values from `id -u` and `id -g`.

Production settings fail closed: the apps refuse to start with `DJANGO_DEBUG=false` unless a secret key is supplied, and compose requires both `BROWSER_SECRET_KEY` and `MANAGER_SECRET_KEY`.

### Environment

All settings are environment-driven. See `.env.example` for the full list. The important values are:

| Variable | Purpose |
| --- | --- |
| `KWC_WALLPAPER_HOST_DIR` | Host folder mounted into both containers |
| `KWC_MANAGER_DATA_DIR` | Host folder for the manager's SQLite database |
| `KWC_IMPORT_HOST_DIR` / `KWC_INGEST_HOST_DIR` | Read-only import and video source folders |
| `TMDB_READ_TOKEN` | TMDB v3 token used by the folder manager |
| `MANAGER_OIDC_*` / `MANAGER_ALLOWED_EMAILS` | Pocket ID (or any OIDC) client and the login allowlist |
| `KWC_TAKEDOWN_EMAIL` | Contact address shown on the public browser |
| `KWC_BROWSER_CACHE_MAX_BYTES` | AVIF derivative cache limit (default 5 GiB) |
| `KWC_UID` / `KWC_GID` | Host user/group used by both containers |
| `BROWSER_SECRET_KEY` / `MANAGER_SECRET_KEY` | Required Django secret keys |
| `BROWSER_ALLOWED_HOSTS` / `MANAGER_ALLOWED_HOSTS` | Comma-separated host names |
| `BROWSER_CSRF_TRUSTED_ORIGINS` / `MANAGER_CSRF_TRUSTED_ORIGINS` | Comma-separated origins when behind HTTPS |
| `BROWSER_BEHIND_PROXY` / `MANAGER_BEHIND_PROXY` | Trust `X-Forwarded-Proto` from a TLS-terminating proxy |
| `MANAGER_BIND` | Host interface for the manager port (default `127.0.0.1`) |
| `MANAGER_WEB_CONCURRENCY` | Gunicorn workers for the manager (default `1` while on SQLite) |
| `MANAGER_EMAIL_*` | SMTP settings used by the manager once OIDC email is wired |
| `BROWSER_TAG` / `MANAGER_TAG` | Image tags used by compose |

## Images

The release workflow publishes two independent images:

- `ghcr.io/kiinami/kwc-browser`
- `ghcr.io/kiinami/kwc-manager`

Each image contains only its own app's dependencies.

## Versioning and releases

Each app has its own `.bumpversion.toml` and its own version stream:

- `browser-vX.Y.Z`
- `manager-vX.Y.Z`

Bump locally with:

```sh
uv run --group dev bump-my-version bump patch --config-file apps/browser/.bumpversion.toml
uv run --group dev bump-my-version bump patch --config-file apps/manager/.bumpversion.toml
```

Run the **Release** workflow manually and choose `browser`, `manager`, or `both` plus the bump type. It bumps the selected app versions, pushes the tags, builds the images, and creates GitHub releases. Choose `none` to publish the current versions without bumping (useful for the initial `0.1.0` release).

## Checks

```sh
cp .env.example .env
uv run --group dev ruff check --no-fix .
uv run --group dev ruff format --check .
uv run --group dev pytest libs
(cd apps/manager && uv run --group dev --package manager pytest)
(cd apps/browser && uv run --group dev --package browser pytest)
uv run --group dev python apps/browser/manage.py check
uv run --group dev python apps/manager/manage.py check
```

## Notes

- The browser is intentionally stateless: no auth, admin, sessions, or database apps. It caches disposable AVIF derivatives outside the wallpaper folder.
- The manager uses SQLite with a single gunicorn worker and a separate `worker` service; keep both at one concurrent writer.
- The manager requires OIDC; configure Pocket ID (or any OpenID Connect provider) and the email allowlist before exposing it.
- Jobs (imports, series creation, renames, deletes) run in the worker and survive a web restart; interrupted jobs are marked and can be re-run.
- `libs/filesystem`, `libs/media`, and `libs/tmdb` hold the shared archive, image, and metadata logic.
- The dev compose stack runs as `KWC_UID`/`KWC_GID`, keeps its virtualenv and uv cache in `/tmp`, and masks `/app/data` read-only so the browser cannot write wallpapers through the repo mount.
