import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RagChunk, RagDocument
from .retriever import retrieve
from .serializers import RagChunkSerializer, RagDocumentSerializer

logger = logging.getLogger(__name__)


class RagDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    """Lista y detalle de documentos indexados en el RAG."""

    serializer_class = RagDocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RagDocument.objects.all().prefetch_related('chunks')


class RagStatusView(APIView):
    """Estado actual del sistema RAG."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        doc_count = RagDocument.objects.count()
        chunk_count = RagChunk.objects.count()
        embedded_count = RagChunk.objects.filter(embedding__isnull=False).count()

        documents = list(
            RagDocument.objects.values('id', 'title', 'chunks_count', 'updated_at')
        )

        return Response({
            'status': 'ready' if embedded_count > 0 else 'empty',
            'documents': doc_count,
            'chunks_total': chunk_count,
            'chunks_embedded': embedded_count,
            'documents_list': documents,
        })


class RagSearchView(APIView):
    """
    Búsqueda semántica en la base de conocimiento.
    POST { "query": "...", "top_k": 4 }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get('query', '').strip()
        top_k = int(request.data.get('top_k', 4))

        if not query:
            return Response(
                {'error': 'El campo query es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = retrieve(query, top_k=top_k)

        return Response({
            'query': query,
            'results': results,
            'count': len(results),
        })
