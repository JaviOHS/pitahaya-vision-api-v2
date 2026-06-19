from django.conf import settings
from django.db import models
from apps.analysis.models import AnalysisResult

class Farm(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='farms',
    )
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=200, default='', blank=True)

    def __str__(self):
        return self.name
    
class Plot(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='plots')
    name = models.CharField(max_length=120)
    hectares = models.FloatField(default=0.0)
    gps_location = models.CharField(max_length=200, default='', blank=True)
    zone = models.CharField(max_length=100, default='', blank=True)
    rows = models.CharField(max_length=50, default='', blank=True)

    def __str__(self):
        return f'{self.farm.name} - {self.name}'
    
class Context(models.Model):
    plot = models.ForeignKey(Plot, on_delete=models.CASCADE, related_name='contexts')
    plant_key_or_id = models.CharField(max_length=120, default='', blank=True)
    affected_part = models.CharField(max_length=120, default='', blank=True)
    main_symptom = models.TextField(default='', blank=True)
    status = models.CharField(max_length=20, default='desconocida', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Contexto de {self.plot}'
    
class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations',
        null=True, blank=True,
    )
    context = models.ForeignKey(Context, on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)
    title = models.CharField(max_length=200, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Conversación de {self.user.username if self.user else "?"} ({self.created_at:%Y-%m-%d %H:%M})'
    
class ChatMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, default='user')  # 'user' o 'assistant'
    content = models.TextField(blank=True, default='')
    image_type = models.CharField(max_length=100, default='', blank=True)
    image_path = models.CharField(max_length=500, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Mensaje de {self.role} en {self.conversation} ({self.created_at:%Y-%m-%d %H:%M})'
    
class PlantHistory(models.Model):
    context = models.ForeignKey(Context, on_delete=models.CASCADE, related_name='plant_histories')
    analysis_result = models.ForeignKey(AnalysisResult, on_delete=models.SET_NULL, null=True, blank=True)
    final_diagnosis = models.CharField(max_length=255, default='', blank=True)
    treatment_applied = models.TextField(default='', blank=True)
    notes = models.TextField(default='', blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        ctx = self.context
        plant = ctx.plant_key_or_id if ctx else '?'
        plot_name = ctx.plot if ctx else '?'
        return f'Historial de planta {plant} en {plot_name}'
    
    