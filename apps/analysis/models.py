from django.db import models


class AnalysisResult(models.Model):
    conversation = models.ForeignKey('chatbot.Conversation', on_delete=models.SET_NULL, null=True, blank=True, related_name='analysis_results')
    chat_message = models.ForeignKey('chatbot.ChatMessage', on_delete=models.SET_NULL, null=True, blank=True, related_name='analysis_results')
    user = models.ForeignKey('security.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='analysis_results')
    image_path = models.ImageField(upload_to='leaf_uploads/%Y/%m/%d/')
    disease_name_predicted = models.CharField(max_length=120, default='', blank=True)
    confidence = models.FloatField(default=0.0)
    probability = models.FloatField(default=0.0)
    severity = models.CharField(max_length=20, default='desconocida', blank=True)
    analysis_text = models.TextField(default='', blank=True)
    recommendations_text = models.TextField(default='', blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.severity} - {self.disease_name_predicted} ({self.created_at:%Y-%m-%d %H:%M})'
