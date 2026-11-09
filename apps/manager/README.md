# manager

Wallpaper organizer. Writes and reorganizes the wallpaper folder.

- Mounts the wallpaper folder read-write.
- Keeps its own SQLite database for job history and future OIDC accounts.
- OIDC login will be mandatory; `django-allauth` is installed but not configured yet.

Run locally from the repository root:

```sh
cp .env.example .env
uv run python apps/manager/manage.py migrate
uv run python apps/manager/manage.py runserver 0.0.0.0:8081
```

Container image: `ghcr.io/kiinami/kwc-manager`.
