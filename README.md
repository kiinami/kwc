# kwc

Small utility to manage my wallpapers and get new ones.

## Deployment

This app is production-ready with:

- Gunicorn WSGI server (`kwc.wsgi:application`)
- WhiteNoise for efficient static file serving

Environment variables:

- PORT: listen port (default 8000)
- HOST: bind interface (default 0.0.0.0)
- WEB_CONCURRENCY: Gunicorn workers (default 2)
- TIMEOUT: Gunicorn worker timeout (default 60)
- DJANGO_ALLOWED_HOSTS: comma-separated hostnames for Django
- STATIC_ROOT: static files directory (pre-collected at build time in Docker)

Local dev server (insecure):

Use the entrypoint script with `serve`.

Container image runs `prod` by default which executes migrations and starts Gunicorn.