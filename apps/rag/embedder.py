"""
Módulo de embeddings para el sistema RAG.
Usa sentence-transformers con el modelo multilingüe (soporte español nativo).
El modelo se descarga automáticamente en el primer uso y queda cacheado.
"""

import logging
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

# Modelo multilingüe ligero (~420 MB, 384 dimensiones).
# Soporta español de forma nativa — ideal para documentos agrícolas.
EMBEDDING_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'


@lru_cache(maxsize=1)
def _get_model():
    """Carga el modelo una sola vez y lo mantiene en memoria."""
    try:
        from sentence_transformers import SentenceTransformer
        logger.info('Cargando modelo de embeddings: %s', EMBEDDING_MODEL)
        model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info('Modelo de embeddings cargado correctamente')
        return model
    except ImportError:
        logger.error('sentence-transformers no está instalado. Ejecuta: pip install sentence-transformers')
        return None


def embed_texts(texts: list[str]) -> np.ndarray | None:
    """
    Genera embeddings normalizados para una lista de textos.
    Retorna un ndarray de shape (N, 384) o None si el modelo no está disponible.
    """
    model = _get_model()
    if model is None:
        return None
    try:
        vectors = model.encode(
            texts,
            normalize_embeddings=True,   # para cosine similarity con dot product
            show_progress_bar=len(texts) > 10,
            batch_size=32,
        )
        return vectors.astype(np.float32)
    except Exception:
        logger.exception('Error generando embeddings')
        return None


def embed_query(text: str) -> np.ndarray | None:
    """Genera el embedding de una sola consulta."""
    result = embed_texts([text])
    return result[0] if result is not None else None


def embedding_to_bytes(vector: np.ndarray) -> bytes:
    """Serializa un vector float32 a bytes para guardar en la DB."""
    return vector.astype(np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Deserializa bytes desde la DB a un vector float32."""
    return np.frombuffer(data, dtype=np.float32)
