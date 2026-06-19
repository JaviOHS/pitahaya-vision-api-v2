from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AskChatbotView,
    SuggestQuestionsView,
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
    path('suggest/', SuggestQuestionsView.as_view(), name='chatbot-suggest'),
]
