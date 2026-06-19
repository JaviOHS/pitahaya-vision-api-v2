"""
Motor de búsqueda semántica para el sistema RAG.
Calcula similitud coseno entre la consulta y todos los chunks en la DB.
Los embeddings están normalizados, así que cosine = dot product.
"""

import logging

import numpy as np

from .embedder import bytes_to_embedding, embed_query
from .models import RagChunk

logger = logging.getLogger(__name__)

# Umbral mínimo de similitud para incluir un chunk en el contexto
SIMILARITY_THRESHOLD = 0.25


def retrieve(query: str, top_k: int = 4) -> list[dict]:
    """
    Busca los chunks más relevantes para la consulta.

    Retorna lista de dicts con:
        - text: contenido del chunk
        - page: página de origen
        - score: similitud coseno (0-1)
        - document: título del documento
    """
    if not query.strip():
        return []

    query_vec = embed_query(query)
    if query_vec is None:
        logger.warning('No se pudo generar embedding para la consulta — retornando vacío')
        return []

    chunks = list(RagChunk.objects.select_related('document').filter(
        embedding__isnull=False,
        embedding_dim__gt=0,
    ))

    if not chunks:
        logger.info('No hay chunks con embeddings en la DB')
        return []

    scored = []
    for chunk in chunks:
        try:
            chunk_vec = bytes_to_embedding(bytes(chunk.embedding))
            score = float(np.dot(query_vec, chunk_vec))
            if score >= SIMILARITY_THRESHOLD:
                scored.append({
                    'text': chunk.text,
                    'page': chunk.page,
                    'score': score,
                    'document': chunk.document.title,
                })
        except Exception:
            logger.exception('Error procesando chunk id=%s', chunk.pk)
            continue

    scored.sort(key=lambda x: x['score'], reverse=True)
    top = scored[:top_k]

    if top:
        logger.info(
            'RAG: %d chunks relevantes para "%s..." (scores: %s)',
            len(top),
            query[:50],
            [f"{r['score']:.2f}" for r in top],
        )
    else:
        logger.info('RAG: sin chunks por encima del umbral para "%s..."', query[:50])

    return top


def retrieve_text_blocks(query: str, top_k: int = 4) -> list[str]:
    """Versión simplificada que solo retorna los textos de los chunks."""
    results = retrieve(query, top_k=top_k)
    return [r['text'] for r in results]


def build_rag_context(query: str, top_k: int = 4) -> str:
    """
    Construye el bloque de contexto RAG listo para inyectar en el prompt de Gemma.
    Retorna cadena vacía si no hay resultados relevantes.
    """
    chunks = retrieve_text_blocks(query, top_k=top_k)
    if not chunks:
        return ''

    lines = ['CONOCIMIENTO BASE — ENFERMEDADES DE PITAHAYA:']
    for i, text in enumerate(chunks, 1):
        lines.append(f'[{i}] {text}')

    return '\n'.join(lines)
