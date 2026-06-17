from django.contrib import admin

from .models import AnalysisResult


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'disease_name_predicted', 'severity',
        'confidence', 'created_at',
    )
    list_filter = ('severity', 'created_at')
    search_fields = ('disease_name_predicted', 'user__username', 'user__email')
    readonly_fields = (
        'disease_name_predicted', 'confidence', 'probability',
        'severity', 'analysis_text', 'recommendations_text', 'created_at',
    )
    ordering = ('-created_at',)
