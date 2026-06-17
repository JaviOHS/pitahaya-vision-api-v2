from rest_framework import serializers
from .models import Context, Farm, PlantHistory, Plot, Conversation, ChatMessage


class PlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plot
        fields = ['id', 'farm', 'name', 'hectares', 'gps_location', 'zone', 'rows']
        read_only_fields = ['id']


class FarmSerializer(serializers.ModelSerializer):
    plots = PlotSerializer(many=True, read_only=True)

    class Meta:
        model = Farm
        fields = ['id', 'user', 'name', 'location', 'plots']
        read_only_fields = ['id', 'user']


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'conversation', 'role', 'content', 'image_type', 'image_path', 'created_at']
        read_only_fields = ['id', 'created_at']


class ContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = Context
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class PlantHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantHistory
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ConversationSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'user', 'context', 'title', 'created_at', 'updated_at', 'messages']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
