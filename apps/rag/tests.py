import io
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import RagChunk, RagDocument

User = get_user_model()


def _results(response):
    if isinstance(response.data, dict) and 'results' in response.data:
        return response.data['results']
    if isinstance(response.data, list):
        return response.data
    return []



class RagDocumentModelTests(TestCase):
    def test_crear_documento(self):
        doc = RagDocument.objects.create(
            title='Enfermedades Pitahaya',
            source_path='/tmp/test.pdf',
            file_hash='abc123',
            chunks_count=10,
        )
        self.assertEqual(str(doc), 'Enfermedades Pitahaya')
        self.assertEqual(doc.chunks_count, 10)

    def test_db_table(self):
        self.assertEqual(RagDocument._meta.db_table, 'RAG_DOCUMENT')

    def test_ordering(self):
        RagDocument.objects.create(
            title='Doc 1', source_path='/tmp/1.pdf', chunks_count=0,
        )
        RagDocument.objects.create(
            title='Doc 2', source_path='/tmp/2.pdf', chunks_count=0,
        )
        qs = RagDocument.objects.all()
        self.assertEqual(qs.first().title, 'Doc 2')


class RagChunkModelTests(TestCase):
    def setUp(self):
        self.doc = RagDocument.objects.create(
            title='Doc Test', source_path='/tmp/test.pdf', chunks_count=1,
        )

    def test_crear_chunk(self):
        chunk = RagChunk.objects.create(
            document=self.doc,
            chunk_index=0,
            text='Las hojas presentan manchas marrones.',
            page=1,
            embedding=np.array([0.1, 0.2, 0.3], dtype=np.float32).tobytes(),
            embedding_dim=3,
            embedding_model='test-model',
        )
        self.assertIn('Doc Test', str(chunk))
        self.assertEqual(chunk.chunk_index, 0)

    def test_unique_together(self):
        RagChunk.objects.create(document=self.doc, chunk_index=0)
        with self.assertRaises(Exception):
            RagChunk.objects.create(document=self.doc, chunk_index=0)

    def test_db_table(self):
        self.assertEqual(RagChunk._meta.db_table, 'RAG_CHUNK')

    def test_chunk_document_relation(self):
        RagChunk.objects.create(document=self.doc, chunk_index=0)
        RagChunk.objects.create(document=self.doc, chunk_index=1)
        self.assertEqual(self.doc.chunks.count(), 2)



class RagSerializersTests(TestCase):
    def test_rag_chunk_serializer(self):
        from .serializers import RagChunkSerializer
        doc = RagDocument.objects.create(
            title='Test', source_path='/tmp/t.pdf', chunks_count=0,
        )
        chunk = RagChunk.objects.create(
            document=doc, chunk_index=0, text='Contenido del chunk', page=1,
            embedding_dim=384, embedding_model='test',
        )
        serializer = RagChunkSerializer(instance=chunk)
        self.assertEqual(serializer.data['text'], 'Contenido del chunk')
        self.assertEqual(serializer.data['page'], 1)
        self.assertNotIn('embedding', serializer.data)

    def test_rag_document_serializer(self):
        from .serializers import RagDocumentSerializer
        doc = RagDocument.objects.create(
            title='Doc Test', source_path='/tmp/d.pdf', chunks_count=2,
        )
        RagChunk.objects.create(document=doc, chunk_index=0, text='Chunk 1')
        RagChunk.objects.create(document=doc, chunk_index=1, text='Chunk 2')
        serializer = RagDocumentSerializer(instance=doc)
        self.assertEqual(len(serializer.data['chunks']), 2)
        self.assertEqual(serializer.data['title'], 'Doc Test')



class RagViewsBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='rag_user', password='Pass1234!',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.doc = RagDocument.objects.create(
            title='Base de conocimiento',
            source_path='/tmp/kb.pdf',
            chunks_count=3,
        )
        self.chunk1 = RagChunk.objects.create(
            document=self.doc, chunk_index=0,
            text='La antracnosis es un hongo que afecta la pitahaya.',
            page=1,
            embedding=np.array([0.1] * 384, dtype=np.float32).tobytes(),
            embedding_dim=384,
            embedding_model='test-model',
        )
        self.chunk2 = RagChunk.objects.create(
            document=self.doc, chunk_index=1,
            text='El mildiu polvoso se presenta como polvo blanco.',
            page=2,
            embedding=np.array([0.2] * 384, dtype=np.float32).tobytes(),
            embedding_dim=384,
            embedding_model='test-model',
        )


class RagDocumentViewSetTests(RagViewsBase):
    def test_list_documents(self):
        response = self.client.get('/api/v2/rag/documents/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(_results(response)), 1)

    def test_document_detail(self):
        response = self.client.get(f'/api/v2/rag/documents/{self.doc.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Base de conocimiento')

    def test_document_chunks_incluidos(self):
        response = self.client.get(f'/api/v2/rag/documents/{self.doc.pk}/')
        self.assertEqual(len(response.data['chunks']), 2)

    def test_read_only_no_post(self):
        response = self.client.post('/api/v2/rag/documents/', {}, format='json')
        self.assertEqual(response.status_code, 405)

    def test_no_autenticado_rechaza(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v2/rag/documents/')
        self.assertEqual(response.status_code, 401)


class RagStatusViewTests(RagViewsBase):
    def test_status_ready(self):
        response = self.client.get('/api/v2/rag/status/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ready')
        self.assertEqual(data['documents'], 1)
        self.assertEqual(data['chunks_total'], 2)
        self.assertEqual(data['chunks_embedded'], 2)

    def test_status_empty(self):
        RagChunk.objects.all().delete()
        RagDocument.objects.all().delete()
        response = self.client.get('/api/v2/rag/status/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'empty')

    def test_status_no_autenticado(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v2/rag/status/')
        self.assertEqual(response.status_code, 401)


class RagSearchViewTests(RagViewsBase):
    @patch('apps.rag.views.retrieve')
    def test_search_simple(self, mock_retrieve):
        mock_retrieve.return_value = [
            {
                'text': 'La antracnosis es un hongo.',
                'page': 1, 'score': 0.85,
                'document': 'Base de conocimiento',
            },
        ]
        response = self.client.post('/api/v2/rag/search/', {
            'query': 'antracnosis',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['query'], 'antracnosis')
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['count'], 1)

    def test_search_sin_query(self):
        response = self.client.post('/api/v2/rag/search/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_search_no_autenticado(self):
        self.client.force_authenticate(user=None)
        response = self.client.post('/api/v2/rag/search/', {
            'query': 'test',
        }, format='json')
        self.assertEqual(response.status_code, 401)



class LoaderTests(TestCase):
    def test_load_markdown(self):
        from .loader import load_markdown
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Enfermedades\nLa antracnosis es común.')
            path = f.name
        try:
            result = load_markdown(path)
            self.assertEqual(len(result), 1)
            self.assertIn('antracnosis', result[0]['text'])
        finally:
            os.unlink(path)

    def test_file_hash(self):
        from .loader import file_hash
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'contenido de prueba')
            path = f.name
        try:
            h = file_hash(path)
            self.assertEqual(len(h), 64)
            self.assertTrue(all(c in '0123456789abcdef' for c in h))
        finally:
            os.unlink(path)

    def test_chunk_pages_basico(self):
        from .loader import chunk_pages
        text = '. '.join(['Enfermedad de pitahaya numero ' + str(i) for i in range(50)])
        pages = [{'text': text, 'page': 1}]
        chunks = chunk_pages(pages)
        self.assertGreater(len(chunks), 0)
        for c in chunks:
            self.assertIn('text', c)
            self.assertIn('page', c)
            self.assertIn('chunk_index', c)

    def test_chunk_pages_vacio(self):
        from .loader import chunk_pages
        self.assertEqual(chunk_pages([]), [])

    def test_load_document_pdf_no_existe_retorna_vacio(self):
        from .loader import load_document
        result = load_document('/tmp/no_existe.pdf')
        self.assertEqual(result, [])

    def test_load_document_markdown(self):
        from .loader import load_document
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Test\nContenido.')
            path = f.name
        try:
            result = load_document(path)
            self.assertGreater(len(result), 0)
        finally:
            os.unlink(path)

    def test_clean_text(self):
        from .loader import _clean_text
        text = 'Hello\x00World   Extra\n\n\nspaces'
        cleaned = _clean_text(text)
        self.assertNotIn('\x00', cleaned)
        self.assertNotIn('   ', cleaned)
        self.assertNotIn('\n\n\n', cleaned)

    def test_split_sentences(self):
        from .loader import _split_sentences
        text = 'Frase una. Frase dos. Frase tres?'
        sentences = _split_sentences(text)
        self.assertGreaterEqual(len(sentences), 3)



class EmbedderTests(TestCase):
    def setUp(self):
        self.embedding_vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    @patch('apps.rag.embedder._get_model')
    def test_embed_texts_exitoso(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([self.embedding_vector])
        mock_get_model.return_value = mock_model

        from .embedder import embed_texts
        result = embed_texts(['texto de prueba'])
        self.assertIsNotNone(result)
        np.testing.assert_array_almost_equal(result[0], self.embedding_vector)

    @patch('apps.rag.embedder._get_model', return_value=None)
    def test_embed_texts_sin_modelo(self, mock_get_model):
        from .embedder import embed_texts
        result = embed_texts(['texto'])
        self.assertIsNone(result)

    def test_embedding_to_bytes_y_back(self):
        from .embedder import embedding_to_bytes, bytes_to_embedding
        original = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        b = embedding_to_bytes(original)
        recovered = bytes_to_embedding(b)
        np.testing.assert_array_almost_equal(original, recovered)

    @patch('apps.rag.embedder._get_model')
    def test_embed_query(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([self.embedding_vector])
        mock_get_model.return_value = mock_model

        from .embedder import embed_query
        result = embed_query('test query')
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)



class RetrieverTests(TestCase):
    def setUp(self):
        self.doc = RagDocument.objects.create(
            title='Test Doc', source_path='/tmp/t.pdf', chunks_count=1,
        )
        self.chunk = RagChunk.objects.create(
            document=self.doc, chunk_index=0,
            text='La antracnosis afecta la pitahaya.',
            page=1,
            embedding=np.array([0.1] * 384, dtype=np.float32).tobytes(),
            embedding_dim=384,
            embedding_model='test-model',
        )

    @patch('apps.rag.retriever.embed_query')
    def test_retrieve_sin_resultados_si_no_hay_coincidencia(self, mock_embed):
        mock_embed.return_value = np.array([0.0] * 384, dtype=np.float32)
        from .retriever import retrieve
        results = retrieve('algo sin relación')
        self.assertEqual(len(results), 0)

    def test_retrieve_query_vacia(self):
        from .retriever import retrieve
        results = retrieve('')
        self.assertEqual(results, [])

    @patch('apps.rag.retriever.embed_query', return_value=None)
    def test_retrieve_sin_embedding(self, mock_embed):
        from .retriever import retrieve
        results = retrieve('test')
        self.assertEqual(results, [])

    def test_retrieve_sin_chunks_en_db(self):
        RagChunk.objects.all().delete()
        from .retriever import retrieve
        results = retrieve('test')
        self.assertEqual(results, [])

    @patch('apps.rag.retriever.embed_query')
    def test_retrieve_con_resultados(self, mock_embed):
        mock_embed.return_value = np.array([0.1] * 384, dtype=np.float32)
        from .retriever import retrieve
        results = retrieve('antracnosis')
        self.assertGreater(len(results), 0)
        self.assertIn('antracnosis', results[0]['text'].lower())

    @patch('apps.rag.retriever.retrieve')
    def test_build_rag_context_vacio(self, mock_retrieve):
        mock_retrieve.return_value = []
        from .retriever import build_rag_context
        result = build_rag_context('test')
        self.assertEqual(result, '')

    @patch('apps.rag.retriever.retrieve')
    def test_build_rag_context_con_resultados(self, mock_retrieve):
        mock_retrieve.return_value = [
            {'text': 'La antracnosis es un hongo.', 'page': 1, 'score': 0.9, 'document': 'Doc'},
        ]
        from .retriever import build_rag_context
        result = build_rag_context('antracnosis')
        self.assertIn('CONOCIMIENTO BASE', result)
        self.assertIn('antracnosis', result)
