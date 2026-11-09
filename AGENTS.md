# kwc agent notes

## Shape

- uv workspace, Python 3.14. Members are `apps/*` and `libs/*`.
- `apps/browser`: public, read-only wallpaper browser. Stateless by design: no DB, auth, admin, sessions, or writes to the wallpaper folder.
- `apps/manager`: writes/organizes the wallpaper folder. Owns SQLite persistence and the future mandatory OIDC login.
- The apps never import each other. The wallpaper folder is the only contract.
- Default host paths are `data/wallpapers` and `data/manager`.
- `libs/filesystem` is a placeholder for the shared folder layout, not a finished API. New shared code belongs under `libs/`; add a `[tool.uv.sources]` entry when an app depends on a library.
- There are no product routes yet: `/` returns 404 and the manager exposes only `/admin/`.
- The old `choose`/`extract`/`kwc` monolith is gone from `main`. For reference, use `legacy-main` (`git show legacy-main`).

## Commands

```sh
uv sync
cp .env.example .env          # local-only debug settings and throwaway secret

# Run locally
uv run python apps/browser/manage.py runserver 0.0.0.0:8080
uv run python apps/manager/manage.py migrate
uv run python apps/manager/manage.py runserver 0.0.0.0:8081

# Checks (run before pushing)
uv lock --check
uv run --group dev ruff check --no-fix .
uv run --group dev ruff format --check .
uv run --group dev python apps/browser/manage.py check
uv run --group dev python apps/manager/manage.py check

# Prove per-app dependency isolation (same as CI)
uv sync --frozen --group dev --package browser
uv run --group dev --package browser python apps/browser/manage.py check
uv sync --frozen --group dev --package manager
uv run --group dev --package manager python apps/manager/manage.py check

# Hooks and containers
uv run --group dev prek run --all-files
docker compose -f docker-compose.dev.yml up
docker compose up -d --build
```

- There is no pytest, mypy, or test suite yet. CI runs lock/ruff/Django checks plus Docker builds; do not claim tests passed.
- Version bumps are per app and also update `uv.lock`:
  `uv run --group dev bump-my-version bump patch --config-file apps/browser/.bumpversion.toml`
  (same for `apps/manager`). The release workflow supports `bump-type=none` to publish current versions.

## Gotchas

- `DJANGO_SECRET_KEY` is required when `DJANGO_DEBUG=false`; compose requires `BROWSER_SECRET_KEY` and `MANAGER_SECRET_KEY`. Without `.env`, `manage.py check` fails unless `DJANGO_DEBUG=true` or a secret is exported.
- `.env` is user-owned and gitignored. Edit `.env.example`, never commit `.env` or real wallpaper/database data; only `data/**/.gitkeep` is tracked.
- Django 6.1 rejects legacy `EMAIL_*` settings when `MAILERS` is defined. Manager mail uses `MAILERS`/`OPTIONS`: console in debug, SMTP in production.
- Settings use `REPO_ROOT = BASE_DIR.parent.parent`: locally `<repo>/apps/<app>`, in containers `/app`. Do not replace it with `parents[1]`.
- Docker build context is the repo root; Dockerfiles live at `apps/*/Dockerfile`. Each image installs only its selected app, flattens it to `/app`, and runs `collectstatic` at build time. Entrypoints do not collect static.
- The browser image runs with a read-only root filesystem; `HOME=/tmp` lets gunicorn write its control socket. Any new runtime write needs a tmpfs or volume.
- Dev compose runs as `KWC_UID`/`KWC_GID`, keeps the venv and uv cache in `/tmp`, and mounts `/app/data` read-only. Set `KWC_UID`/`KWC_GID` if your host user is not 1000.
- Manager uses SQLite with one gunicorn worker by default. Raise `MANAGER_WEB_CONCURRENCY` only after moving to Postgres.
- Manager binds `127.0.0.1` by default; use `MANAGER_BIND=0.0.0.0` only behind a reverse proxy. OIDC is not implemented yet; `django-allauth` is installed in manager but not wired.
- CI freezes `uv.lock`; run `uv lock` after workspace or dependency changes. Bump configs update `pyproject.toml` and `{repo_root}/uv.lock`, so do not hand-edit versions.
- Releases run only from `main`; tags are `browser-vX.Y.Z` / `manager-vX.Y.Z`; images are `ghcr.io/kiinami/kwc-browser` and `ghcr.io/kiinami/kwc-manager`.
- This checkout's repo-local git email is the GitHub noreply address; personal emails are rejected by GitHub push protection.

## Working conventions

- Conventional Commits, scoped when useful (`feat(browser): ...`).
- Work on a feature branch and PR to `main` unless the user explicitly asks for a direct push.
- Prefer deleting obsolete code over compatibility shims.
- Verify with the checks above before pushing; CI is the final gate.
