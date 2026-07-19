from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AskChatbotView,
    ExportBackupView,
    ImportBackupView,
    StreamChatbotView,
    SuggestQuestionsView,
    HeatmapAnalysisView,
    ContextViewSet,
    FarmViewSet,
    PlantHistoryViewSet,
    PlotViewSet,
    ConversationViewSet,
    ChatMessageViewSet,
)

router = DefaultRouter()
router.register(r'farms', FarmViewSet, basename='farm')
router.register(r'plots', PlotViewSet, basename='plot')
router.register(r'contexts', ContextViewSet, basename='context')
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', ChatMessageViewSet, basename='message')
router.register(r'plant-histories', PlantHistoryViewSet, basename='plant-history')

urlpatterns = [
    path('', include(router.urls)),
    path('chat/', AskChatbotView.as_view(), name='chatbot-ask'),
    path('chat/stream/', StreamChatbotView.as_view(), name='chatbot-ask-stream'),
    path('suggest/', SuggestQuestionsView.as_view(), name='chatbot-suggest'),
    path('heatmap-analysis/', HeatmapAnalysisView.as_view(), name='chatbot-heatmap-analysis'),
    path('import-backup/', ImportBackupView.as_view(), name='chatbot-import-backup'),
    path('export-backup/', ExportBackupView.as_view(), name='chatbot-export-backup'),
]
