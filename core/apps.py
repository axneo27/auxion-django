from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Initialize Firebase Admin SDK when app is ready
        try:
            from . import firebase  # noqa: F401 - triggers initialization
        except Exception:
            # Avoid crashing app startup if firebase config missing; views handle auth usage.
            pass
