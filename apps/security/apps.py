from django.apps import AppConfig


class SecurityConfig(AppConfig):
    name = 'apps.security'

    def ready(self):
        import apps.security.signals
