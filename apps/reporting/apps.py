from django.apps import AppConfig


class ReportingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reporting"
    verbose_name = "Gestión e informes"

    def ready(self):
        from . import signals  # noqa: F401
