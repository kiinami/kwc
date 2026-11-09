from django.apps import AppConfig


class ImporterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "importer"

    def ready(self) -> None:
        from . import jobs  # noqa: F401  (registers job handlers)
