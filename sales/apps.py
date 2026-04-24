from django.apps import AppConfig


class SalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sales"

    def ready(self):
        # Register meta-cache invalidation signal hooks.
        from sales import signals_meta_cache  # noqa: F401

        # Register providers when app loads
        from sales.services.providers import register_all_providers
        register_all_providers()
