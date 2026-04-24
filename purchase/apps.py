from django.apps import AppConfig


class PurchaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "purchase"

    def ready(self):
        # Register meta-cache invalidation signal hooks.
        from purchase import signals_meta_cache  # noqa: F401
