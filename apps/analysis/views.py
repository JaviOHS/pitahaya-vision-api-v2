import logging
import urllib.request
import urllib.parse
import json as _json
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from .models import AnalysisResult
from .serializers import AnalysisResultSerializer
from .services import classify_leaf
from apps.security.permissions import is_admin as _is_admin
from apps.chatbot.models import PlantHistory

logger = logging.getLogger(__name__)


def _filter_by_range(queryset, range_filter, date_from='', date_to=''):
    today = timezone.localdate()
    range_filter = (range_filter or 'all').strip().lower()

    if range_filter == 'today':
        queryset = queryset.filter(created_at__date=today)
    elif range_filter == 'last7':
        queryset = queryset.filter(
            created_at__date__gte=today - timedelta(days=6),
            created_at__date__lte=today,
        )
    elif range_filter == 'month':
        queryset = queryset.filter(created_at__year=today.year, created_at__month=today.month)

    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    return queryset


def _filter_by_full_name(queryset, query):
    query = (query or '').strip()
    if not query:
        return queryset
    tokens = [t for t in query.split() if t]
    for token in tokens:
        queryset = queryset.filter(
            Q(user__first_name__icontains=token)
            | Q(user__last_name__icontains=token)
        )
    return queryset


class AnalysisListCreateView(generics.ListCreateAPIView):
    serializer_class = AnalysisResultSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = None

    def get_queryset(self):
        qs = AnalysisResult.objects.select_related('user').all()
        if not _is_admin(self.request.user):
            qs = qs.filter(user=self.request.user)

        params = self.request.query_params
        range_filter = params.get('range', 'all').strip().lower()
        date_from = params.get('date_from', '').strip()
        date_to = params.get('date_to', '').strip()
        user_query = params.get('user_name', '').strip()

        qs = _filter_by_range(qs, range_filter, date_from, date_to)

        if _is_admin(self.request.user) and user_query:
            qs = _filter_by_full_name(qs, user_query)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        conversation_id = self.request.data.get('conversation')
        try:
            lat = float(self.request.data.get('latitude') or '')
        except (ValueError, TypeError):
            lat = None
        try:
            lon = float(self.request.data.get('longitude') or '')
        except (ValueError, TypeError):
            lon = None
        instance = serializer.save(
            user=self.request.user,
            conversation_id=conversation_id if conversation_id else None,
            latitude=lat,
            longitude=lon,
        )
        try:
            instance.image_path.open('rb')
            prediction = classify_leaf(instance.image_path)
            instance.image_path.close()
            instance.severity = prediction.get('status', 'desconocida')
            instance.disease_name_predicted = prediction.get('disease_name', '')
            instance.confidence = float(prediction.get('confidence', 0.0) or 0.0)
            instance.recommendations_text = prediction.get('recommendation', '')
            instance.save(update_fields=[
                'severity', 'disease_name_predicted', 'confidence', 'recommendations_text',
            ])
        except Exception as exc:
            logger.exception('Error al clasificar imagen: %s', exc)

        # ── Create PlantHistory if a conversation is linked ──
        if instance.conversation and instance.conversation.context:
            try:
                PlantHistory.objects.create(
                    context=instance.conversation.context,
                    analysis_result=instance,
                    final_diagnosis=instance.disease_name_predicted,
                    treatment_applied=instance.recommendations_text,
                    notes=instance.analysis_text,
                )
            except Exception as exc:
                logger.exception('Error al crear PlantHistory: %s', exc)


class AnalysisDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AnalysisResultSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = AnalysisResult.objects.select_related('user').all()
        if not _is_admin(self.request.user):
            qs = qs.filter(user=self.request.user)
        return qs


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def weather_proxy(request):
    lat = request.query_params.get('lat', '').strip()
    lon = request.query_params.get('lon', '').strip()
    if not lat or not lon:
        return Response({'error': 'lat y lon son requeridos'}, status=400)

    api_key = settings.VISUAL_CROSSING_API_KEY
    if not api_key:
        return Response({'error': 'API key no configurada'}, status=503)

    params = urllib.parse.urlencode({
        'unitGroup': 'metric',
        'key': api_key,
        'include': 'days',
        'elements': 'datetime,precip,humidity,temp,tempmin,tempmax,windspeed',
        'contentType': 'json',
    })
    url = f'https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/last3days?{params}'

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
    except Exception as e:
        logger.warning('WeatherProxy error: %s', e)
        return Response({'error': 'No se pudo obtener el clima'}, status=502)

    days = data.get('days', [])
    if not days:
        return Response({'error': 'Sin datos de clima'}, status=502)

    total_precip = sum(d.get('precip') or 0 for d in days)
    avg_humidity = sum(d.get('humidity') or 0 for d in days) / len(days)
    avg_temp = sum(d.get('temp') or 0 for d in days) / len(days)
    avg_wind = sum(d.get('windspeed') or 0 for d in days) / len(days)
    temp_min = min((d.get('tempmin') or d.get('temp') or 0) for d in days)
    temp_max = max((d.get('tempmax') or d.get('temp') or 0) for d in days)

    if total_precip > 10:
        condition = 'Lluvioso'
    elif avg_humidity > 75:
        condition = 'Húmedo sin lluvia'
    elif total_precip < 1 and avg_humidity < 60:
        condition = 'Período seco'
    else:
        condition = 'Normal para la época'

    days_out = [
        {
            'date':     d.get('datetime', ''),
            'temp':     round(d.get('temp') or 0, 1),
            'tempMin':  round(d.get('tempmin') or d.get('temp') or 0, 1),
            'tempMax':  round(d.get('tempmax') or d.get('temp') or 0, 1),
            'precip':   round(d.get('precip') or 0, 1),
            'humidity': round(d.get('humidity') or 0),
            'wind':     round(d.get('windspeed') or 0, 1),
        }
        for d in days
    ]

    return Response({
        'totalPrecip': round(total_precip, 1),
        'avgHumidity': round(avg_humidity),
        'avgTemp':     round(avg_temp, 1),
        'tempMin':     round(temp_min, 1),
        'tempMax':     round(temp_max, 1),
        'avgWind':     round(avg_wind, 1),
        'condition':   condition,
        'days':        days_out,
    })
