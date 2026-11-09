# browser

Public, read-only wallpaper browser and downloader.

- Reads the wallpaper folder. Never writes to it.
- Stateless: no database, no login, no admin.
- Preferences such as light/dark mode live in cookies.

Run locally from the repository root:

```sh
cp .env.example .env
uv run python apps/browser/manage.py runserver 0.0.0.0:8080
```

Container image: `ghcr.io/kiinami/kwc-browser`.
