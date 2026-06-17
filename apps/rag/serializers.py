from rest_framework import serializers
from .models import RagDocument, RagChunk


class RagChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = RagChunk
        fields = ['id', 'document', 'chunk_index', 'text', 'page', 'embedding_dim', 'embedding_model', 'created_at']
        read_only_fields = ['id', 'created_at']


class RagDocumentSerializer(serializers.ModelSerializer):
    chunks = RagChunkSerializer(many=True, read_only=True)

    class Meta:
        model = RagDocument
        fields = ['id', 'title', 'source_path', 'file_hash', 'chunks_count', 'chunks', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
