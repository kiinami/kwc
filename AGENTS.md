# kwc agent notes

## Shape

- uv workspace, Python 3.14. Members are `apps/*` and `libs/*`.
- `apps/browser`: public, read-only wallpaper browser. Stateless by design: no DB, auth, admin, sessions, or writes to the wallpaper folder.
- `apps/manager`: writes/organizes the wallpaper folder. Owns SQLite persistence and the mandatory OIDC login with an email allowlist.
- The apps never import each other. The wallpaper folder is the only contract.
- Default host paths are `data/wallpapers` and `data/manager`.
- Shared code lives under `libs/`: `filesystem` (scan, metadata, ordering, safe paths), `media` (JPEG XL/AVIF, hashes, EXIF), and `tmdb` (read-only client). Add a `[tool.uv.sources]` entry when an app depends on a library.
- Routes: browser serves the gallery at `/`, plus `/browse/<path>`, `/view/<path>`, `/i|t|l/<path>` originals/thumbnails/lens images, `/downloads.json`, and `/takedown`. Manager serves `/admin/`, `/accounts/` (OIDC), `/healthz`, `/jobs`, `/folders/*`, and `/importer*`.
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

# Tests (per package: app tests must run from their own directory)
uv run --group dev pytest libs
(cd apps/manager && DJANGO_DEBUG=true DJANGO_SECRET_KEY=dev uv run --group dev --package manager pytest)
(cd apps/browser && DJANGO_DEBUG=true DJANGO_SECRET_KEY=dev uv run --group dev --package browser pytest)

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

- pytest covers the shared libraries and both apps. There is no mypy yet. CI runs lock/ruff/Django checks, the test suites, and Docker builds; run the tests before claiming anything passes.
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
- Manager binds `127.0.0.1` by default; use `MANAGER_BIND=0.0.0.0` only behind a reverse proxy. OIDC is wired through `django-allauth`'s `openid_connect` provider; set `MANAGER_OIDC_ISSUER`/`CLIENT_ID`/`CLIENT_SECRET` and allow emails with `MANAGER_ALLOWED_EMAILS`. Local signup stays closed.
- CI freezes `uv.lock`; run `uv lock` after workspace or dependency changes. Bump configs update `pyproject.toml` and `{repo_root}/uv.lock`, so do not hand-edit versions.
- Releases run only from `main`; tags are `browser-vX.Y.Z` / `manager-vX.Y.Z`; images are `ghcr.io/kiinami/kwc-browser` and `ghcr.io/kiinami/kwc-manager`.
- This checkout's repo-local git email is the GitHub noreply address; personal emails are rejected by GitHub push protection.

## Working conventions

- Conventional Commits, scoped when useful (`feat(browser): ...`).
- Code and behavior changes go on a feature branch and PR to `main`. Documentation-only changes (`AGENTS.md`, `README.md`, specs) may be pushed directly to `main` without a PR, unless the user asks otherwise.
- Prefer deleting obsolete code over compatibility shims.
- Verify with the checks above before pushing; CI is the final gate.
