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
    plant_key = serializers.SerializerMethodField()
    context_detail = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    disease_name_predicted = serializers.SerializerMethodField()

    class Meta:
        model = PlantHistory
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_plant_key(self, obj):
        if not obj.context:
            return ''
        ctx = obj.context
        plant = ctx.plant_key_or_id or (f'plot_{ctx.plot_id}' if ctx.plot_id else '')
        plot = str(ctx.plot_id) if ctx.plot_id else ''
        if not plant and not plot:
            return ''
        return f'{plant}|{plot}'

    def get_context_detail(self, obj):
        if not obj.context:
            return None
        ctx = obj.context
        plot = ctx.plot if ctx.plot_id else None
        farm = plot.farm if plot and plot.farm_id else None
        return {
            'id': ctx.id,
            'plant_key_or_id': ctx.plant_key_or_id or '',
            'affected_part': ctx.affected_part or '',
            'main_symptom': ctx.main_symptom or '',
            'status': ctx.status or '',
            'farm_name': farm.name if farm else '',
            'farm_id': farm.id if farm else None,
            'plot_id': plot.id if plot else None,
            'plot_name': plot.name if plot else '',
            'zone': plot.zone if plot else '',
            'rows': plot.rows if plot else '',
            'created_at': ctx.created_at.isoformat() if ctx.created_at else '',
        }

    def get_severity(self, obj):
        if obj.analysis_result and obj.analysis_result.severity:
            return obj.analysis_result.severity
        if obj.context and obj.context.status:
            return obj.context.status
        return ''

    def get_disease_name_predicted(self, obj):
        if obj.analysis_result and obj.analysis_result.disease_name_predicted:
            return obj.analysis_result.disease_name_predicted
        return obj.final_diagnosis or ''


class ConversationSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'user', 'context', 'title', 'created_at', 'updated_at', 'messages']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
