from rest_framework import serializers

from .models import AnalysisResult

MAX_IMAGE_SIZE = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}


class AnalysisResultSerializer(serializers.ModelSerializer):
    image_path = serializers.ImageField(write_only=True, required=True)
    image_url = serializers.SerializerMethodField()
    confidence_percent = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()

    def validate_conversation(self, value):
        request = self.context.get('request')
        if value and request and value.user_id != request.user.pk:
            raise serializers.ValidationError(
                'Esta conversación no existe o no te pertenece.'
            )
        return value

    def validate_image_path(self, value):
        if value is None:
            raise serializers.ValidationError('La imagen es obligatoria.')
        if value.size > MAX_IMAGE_SIZE:
            raise serializers.ValidationError('La imagen no puede superar 10 MB.')
        content_type = (getattr(value, 'content_type', '') or '').lower()
        name = (getattr(value, 'name', '') or '').lower()
        extension = name.rsplit('.', 1)[-1] if '.' in name else ''
        if content_type and content_type not in ALLOWED_IMAGE_TYPES:
            raise serializers.ValidationError('Formato no válido. Usa JPG, PNG o WEBP.')
        if extension and extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise serializers.ValidationError('Extensión no válida. Usa JPG, PNG o WEBP.')
        return value

    class Meta:
        model = AnalysisResult
        fields = [
            'id',
            'conversation',
            'chat_message',
            'image_path',
            'image_url',
            'disease_name_predicted',
            'confidence',
            'confidence_percent',
            'probability',
            'severity',
            'analysis_text',
            'recommendations_text',
            'latitude',
            'longitude',
            'created_at',
            'owner_name',
            'owner_email',
        ]
        read_only_fields = [
            'id',
            'image_url',
            'disease_name_predicted',
            'confidence',
            'confidence_percent',
            'probability',
            'severity',
            'analysis_text',
            'recommendations_text',
            'created_at',
            'owner_name',
            'owner_email',
        ]

    def get_image_url(self, obj):
        if not obj.image_path:
            return ''
        request = self.context.get('request')
        url = obj.image_path.url
        return request.build_absolute_uri(url) if request else url

    def get_confidence_percent(self, obj):
        value = obj.confidence or 0
        if value <= 1:
            value = value * 100
        return round(value, 1)

    def get_owner_name(self, obj):
        if not obj.user:
            return ''
        return obj.user.full_name

    def get_owner_email(self, obj):
        if not obj.user:
            return ''
        return obj.user.email
