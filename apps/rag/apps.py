import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class RagConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.rag'
    verbose_name = 'RAG'

    def ready(self):
        from .embedder import _get_model
        logger.info('Precargando modelo de embeddings RAG…')
        _get_model()
        logger.info('Modelo de embeddings RAG listo')
