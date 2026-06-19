"""
Comando de gestión para ingestar documentos en el sistema RAG.

Uso:
    python manage.py ingest_rag <ruta_archivo>        # ingestar un PDF
    python manage.py ingest_rag --auto                # ingestar todo lo de knowledge_base/
    python manage.py ingest_rag <ruta> --force        # re-ingestar aunque no cambió

Ejemplo:
    python manage.py ingest_rag knowledge_base/enfermedades_pitahaya_RAG.md.pdf
"""

import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.rag.embedder import EMBEDDING_MODEL, embed_texts, embedding_to_bytes
from apps.rag.loader import chunk_pages, file_hash, load_document
from apps.rag.models import RagChunk, RagDocument


KNOWLEDGE_BASE_DIR = os.path.join(settings.BASE_DIR, 'knowledge_base')


class Command(BaseCommand):
    help = 'Ingesta documentos PDF/Markdown en la base de conocimiento RAG'

    def add_arguments(self, parser):
        parser.add_argument(
            'path',
            nargs='?',
            type=str,
            help='Ruta al archivo PDF o directorio a ingestar',
        )
        parser.add_argument(
            '--auto',
            action='store_true',
            help='Ingestar automáticamente todos los archivos en knowledge_base/',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-ingestar aunque el hash del archivo no haya cambiado',
        )

    def handle(self, *args, **options):
        paths = []

        if options['auto']:
            if not os.path.isdir(KNOWLEDGE_BASE_DIR):
                raise CommandError(f'Directorio no encontrado: {KNOWLEDGE_BASE_DIR}')
            for fname in os.listdir(KNOWLEDGE_BASE_DIR):
                if fname.lower().endswith(('.pdf', '.md', '.txt')):
                    paths.append(os.path.join(KNOWLEDGE_BASE_DIR, fname))
            if not paths:
                self.stdout.write(self.style.WARNING('No se encontraron archivos en knowledge_base/'))
                return
        elif options['path']:
            paths = [options['path']]
        else:
            raise CommandError('Proporciona una ruta o usa --auto para ingestar knowledge_base/')

        force = options['force']
        total_chunks = 0

        for path in paths:
            if not os.path.isfile(path):
                self.stdout.write(self.style.ERROR(f'Archivo no encontrado: {path}'))
                continue
            chunks = self._ingest_file(path, force=force)
            total_chunks += chunks

        self.stdout.write(self.style.SUCCESS(
            f'\nIngesta completada. Total de chunks: {total_chunks}'
        ))

    def _ingest_file(self, path: str, force: bool = False) -> int:
        abs_path = os.path.abspath(path)
        title = os.path.basename(abs_path)
        fhash = file_hash(abs_path)

        self.stdout.write(f'\nProcesando: {title}')

        existing = RagDocument.objects.filter(source_path=abs_path).first()
        if existing and existing.file_hash == fhash and not force:
            self.stdout.write(
                self.style.WARNING(f'  Sin cambios (mismo hash). Usa --force para re-ingestar.')
            )
            return existing.chunks_count

        if existing:
            self.stdout.write(f'  Eliminando {existing.chunks_count} chunks anteriores...')
            existing.chunks.all().delete()
            doc = existing
        else:
            doc = RagDocument(source_path=abs_path, title=title)

        doc.file_hash = fhash
        doc.chunks_count = 0
        doc.save()

        # 1. Cargar y limpiar el documento
        self.stdout.write('  Cargando documento...')
        pages = load_document(abs_path)
        if not pages:
            self.stdout.write(self.style.ERROR('  No se pudo extraer texto del documento.'))
            return 0

        # 2. Dividir en chunks
        self.stdout.write('  Dividiendo en chunks...')
        chunks = chunk_pages(pages)
        if not chunks:
            self.stdout.write(self.style.ERROR('  No se generaron chunks.'))
            return 0
        self.stdout.write(f'  {len(chunks)} chunks generados.')

        # 3. Generar embeddings
        self.stdout.write(f'  Generando embeddings con {EMBEDDING_MODEL}...')
        t0 = time.time()
        texts = [c['text'] for c in chunks]
        vectors = embed_texts(texts)

        if vectors is None:
            self.stdout.write(self.style.ERROR(
                '  Error generando embeddings. Verifica que sentence-transformers esté instalado.'
            ))
            return 0

        elapsed = time.time() - t0
        self.stdout.write(f'  Embeddings generados en {elapsed:.1f}s')

        # 4. Guardar en DB
        self.stdout.write('  Guardando en base de datos...')
        chunk_objects = [
            RagChunk(
                document=doc,
                chunk_index=chunk['chunk_index'],
                text=chunk['text'],
                page=chunk.get('page', 0),
                embedding=embedding_to_bytes(vectors[i]),
                embedding_dim=int(vectors[i].shape[0]),
                embedding_model=EMBEDDING_MODEL,
            )
            for i, chunk in enumerate(chunks)
        ]

        RagChunk.objects.bulk_create(chunk_objects, batch_size=100)
        doc.chunks_count = len(chunk_objects)
        doc.save()

        self.stdout.write(self.style.SUCCESS(
            f'  OK: {len(chunk_objects)} chunks indexados correctamente'
        ))
        return len(chunk_objects)
