from rest_framework import viewsets, permissions
from rest_framework.permissions import IsAuthenticated

from .models import RagDocument, RagChunk
from .serializers import RagDocumentSerializer, RagChunkSerializer


class RagDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = RagDocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RagDocument.objects.all().prefetch_related('chunks')

    def perform_create(self, serializer):
        serializer.save()


class RagChunkViewSet(viewsets.ModelViewSet):
    serializer_class = RagChunkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RagChunk.objects.all().select_related('document')

    def perform_create(self, serializer):
        serializer.save()
