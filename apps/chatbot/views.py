from rest_framework import viewsets, permissions
from rest_framework.permissions import IsAuthenticated

from .models import Context, Farm, PlantHistory, Plot, Conversation, ChatMessage
from .serializers import ContextSerializer, FarmSerializer, PlantHistorySerializer, PlotSerializer, ConversationSerializer, ChatMessageSerializer


class FarmViewSet(viewsets.ModelViewSet):
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Farm.objects.filter(user=self.request.user).prefetch_related('plots')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PlotViewSet(viewsets.ModelViewSet):
    serializer_class = PlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Plot.objects.filter(farm__user=self.request.user).select_related('farm')

    def perform_create(self, serializer):
        serializer.save()


class ContextViewSet(viewsets.ModelViewSet):
    serializer_class = ContextSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Context.objects.filter(plot__farm__user=self.request.user).select_related('plot__farm')

    def perform_create(self, serializer):
        serializer.save()


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).prefetch_related('messages').order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ChatMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ChatMessage.objects.filter(conversation__user=self.request.user).select_related('conversation')

    def perform_create(self, serializer):
        serializer.save()


class PlantHistoryViewSet(viewsets.ModelViewSet):
    serializer_class = PlantHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PlantHistory.objects.filter(context__plot__farm__user=self.request.user).select_related('context__plot__farm')

    def perform_create(self, serializer):
        serializer.save()
