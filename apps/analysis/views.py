import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import AnalysisResult
from .serializers import AnalysisResultSerializer
from .services import classify_leaf
from apps.security.permissions import is_admin as _is_admin

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
        instance = serializer.save(user=self.request.user)
        try:
            instance.image_path.open('rb')
            prediction = classify_leaf(instance.image_path)
            instance.image_path.close()
            instance.severity = prediction.get('status', 'desconocida')
            instance.disease_name_predicted = prediction.get('disease_name', '')
            instance.confidence = float(prediction.get('confidence', 0.0) or 0.0)
            instance.recommendation_text = prediction.get('recommendation', '')
            instance.save(update_fields=[
                'severity', 'disease_name_predicted', 'confidence', 'recommendation_text',
            ])
        except Exception as exc:
            logger.exception('Error al clasificar imagen: %s', exc)


class AnalysisDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = AnalysisResultSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = AnalysisResult.objects.select_related('user').all()
        if not _is_admin(self.request.user):
            qs = qs.filter(user=self.request.user)
        return qs
