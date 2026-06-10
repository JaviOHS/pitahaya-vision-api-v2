from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    name = 'apps.analysis'

    def ready(self):
        import apps.analysis  # noqa
