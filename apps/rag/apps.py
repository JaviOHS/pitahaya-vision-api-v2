import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class RagConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.rag'
    verbose_name = 'RAG'

    def ready(self):
        if 'runserver' not in sys.argv:
            return
        from .embedder import _get_model
        logger.info('Precargando modelo de embeddings RAG…')
        _get_model()
        logger.info('Modelo de embeddings RAG listo')
