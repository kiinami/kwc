# kwc agent notes

## What this repo is

A uv workspace with two isolated Django apps that share a wallpaper folder:

- `apps/browser` — public, read-only browsing/downloading. No database, no login, no writes to the wallpaper folder.
- `apps/manager` — writes and organizes the wallpaper folder. Will require OIDC login. Keeps its own SQLite database.

The apps do not communicate. The wallpaper folder is the only contract.

## Conventions

- Use uv for everything: `uv sync`, `uv run ...`, `uv lock`.
- Workspace members are `apps/*` and `libs/*`.
- Keep shared concerns in focused libraries under `libs/`; do not make one app import the other.
- Browser settings must stay DB-free unless the product explicitly needs state.
- Manager settings own persistence and authentication.
- Each app has its own version stream and `.bumpversion.toml`.
- New library members are picked up by the `libs/*` workspace glob; add a `[tool.uv.sources]` entry when an app depends on one.

## Useful commands

```sh
uv sync
uv run python apps/browser/manage.py check
uv run python apps/manager/manage.py check
uv run --group dev ruff check .
uv run --group dev ruff format --check .
docker compose -f docker-compose.dev.yml up
docker compose up -d --build
```

## Infrastructure invariants

- Browser container has no DB volume and runs with a read-only root filesystem.
- Manager mounts the wallpaper folder read-write; browser mounts it read-only.
- The dev browser also masks `/app/data` read-only so the repo bind mount cannot be used to write wallpapers.
- Dev containers run as `KWC_UID`/`KWC_GID`; keep their virtualenv and uv cache under `/tmp`.
- Production fails closed without `DJANGO_SECRET_KEY`; compose requires `BROWSER_SECRET_KEY` and `MANAGER_SECRET_KEY`.
- The manager binds to `127.0.0.1` by default until OIDC and a reverse proxy exist.
- Browser and manager images are built separately and published as `ghcr.io/kiinami/kwc-browser` and `ghcr.io/kiinami/kwc-manager`.
- Releases use `browser-vX.Y.Z` and `manager-vX.Y.Z` tags.
- CI checks each app in an isolated uv environment and builds both Docker images.
