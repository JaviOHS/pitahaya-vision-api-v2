"""
Carga documentos PDF y los divide en chunks de texto con superposición.
Estrategia: división por párrafos/oraciones manteniendo coherencia semántica.
"""

import hashlib
import logging
import re

logger = logging.getLogger(__name__)

# Parámetros de chunking
CHUNK_SIZE = 400      # palabras máximas por chunk
CHUNK_OVERLAP = 60    # palabras de superposición entre chunks
MIN_CHUNK_WORDS = 30  # descarta chunks muy cortos (encabezados, etc.)


def file_hash(path: str) -> str:
    """SHA-256 del archivo para detectar cambios y evitar re-ingestión."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8192), b''):
            h.update(block)
    return h.hexdigest()


def load_pdf(path: str) -> list[dict]:
    """
    Extrae texto de un PDF página por página.
    Retorna lista de {text, page}.
    Requiere: pypdf>=4.0
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            text = _clean_text(text)
            if text.strip():
                pages.append({'text': text, 'page': i + 1})
        logger.info('PDF cargado: %d páginas con contenido de %s', len(pages), path)
        return pages
    except ImportError:
        logger.error('pypdf no está instalado. Ejecuta: pip install pypdf')
        return []
    except Exception:
        logger.exception('Error cargando PDF: %s', path)
        return []


def load_markdown(path: str) -> list[dict]:
    """Carga un archivo .md o .txt como un solo bloque."""
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
        text = _clean_text(text)
        return [{'text': text, 'page': 1}]
    except Exception:
        logger.exception('Error cargando archivo de texto: %s', path)
        return []


def load_document(path: str) -> list[dict]:
    """Detecta el tipo de archivo y delega al loader correcto."""
    lower = path.lower()
    if lower.endswith('.pdf'):
        return load_pdf(path)
    if lower.endswith(('.md', '.txt')):
        return load_markdown(path)
    # Intenta PDF por defecto
    return load_pdf(path)


def chunk_pages(pages: list[dict]) -> list[dict]:
    """
    Divide las páginas en chunks con superposición.
    Retorna lista de {text, page, chunk_index}.
    """
    # Unir el texto de todas las páginas conservando metadato de página
    page_segments = []
    for page_data in pages:
        sentences = _split_sentences(page_data['text'])
        for s in sentences:
            if s.strip():
                page_segments.append({'sentence': s.strip(), 'page': page_data['page']})

    if not page_segments:
        return []

    chunks = []
    current_words: list[str] = []
    current_page = page_segments[0]['page']
    chunk_idx = 0

    for seg in page_segments:
        words = seg['sentence'].split()
        if current_words and len(current_words) + len(words) > CHUNK_SIZE:
            # Guardar chunk actual
            chunk_text = ' '.join(current_words)
            if len(current_words) >= MIN_CHUNK_WORDS:
                chunks.append({
                    'text': chunk_text,
                    'page': current_page,
                    'chunk_index': chunk_idx,
                })
                chunk_idx += 1
            # Iniciar siguiente chunk con overlap
            overlap_start = max(0, len(current_words) - CHUNK_OVERLAP)
            current_words = current_words[overlap_start:] + words
        else:
            current_words.extend(words)
        current_page = seg['page']

    # Último chunk
    if len(current_words) >= MIN_CHUNK_WORDS:
        chunks.append({
            'text': ' '.join(current_words),
            'page': current_page,
            'chunk_index': chunk_idx,
        })

    logger.info('Chunks generados: %d', len(chunks))
    return chunks


def _split_sentences(text: str) -> list[str]:
    """Divide texto en oraciones usando puntuación."""
    # Divide en oraciones pero agrupa líneas cortas (encabezados) con la siguiente
    parts = re.split(r'(?<=[.!?:])\s+|\n{2,}', text)
    return [p.strip() for p in parts if p.strip()]


def _clean_text(text: str) -> str:
    """Limpia artefactos comunes de extracción de PDF."""
    # Elimina caracteres de control excepto saltos de línea
    text = re.sub(r'[^\x20-\x7E\xA0-\xFF\n]', ' ', text)
    # Colapsa espacios múltiples
    text = re.sub(r'[ \t]{2,}', ' ', text)
    # Normaliza saltos de línea múltiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
