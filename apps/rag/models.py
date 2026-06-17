from django.db import models


class RagDocument(models.Model):
    title = models.CharField(max_length=255)
    source_path = models.CharField(max_length=500, unique=True)
    file_hash = models.CharField(max_length=255, default='', blank=True)
    chunks_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'RAG_DOCUMENT'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class RagChunk(models.Model):
    document = models.ForeignKey(RagDocument, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.IntegerField()
    text = models.TextField(default='', blank=True)
    page = models.IntegerField(null=True, blank=True)
    embedding = models.BinaryField(null=True, blank=True)
    embedding_dim = models.IntegerField(default=0)
    embedding_model = models.CharField(max_length=255, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'RAG_CHUNK'
        unique_together = [['document', 'chunk_index']]
        ordering = ['document', 'chunk_index']

    def __str__(self):
        return f'{self.document.title} - Chunk {self.chunk_index}'
