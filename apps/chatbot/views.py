import logging
import os
import re
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.models import AnalysisResult
from apps.analysis.serializers import AnalysisResultSerializer
from apps.analysis.services import get_weather_summary
from apps.analysis.views import _filter_by_range
from apps.security.models import Profile
from apps.security.mixins import CurrentUserCreateMixin, OwnerFilterMixin
from apps.security.permissions import is_admin
from apps.security.utils import normalize_name

from . import client as chatbot_client
from .models import Context, Conversation, ChatMessage, Farm, PlantHistory, Plot
from .serializers import (
    ContextSerializer,
    ConversationSerializer,
    ChatMessageSerializer,
    FarmSerializer,
    PlantHistorySerializer,
    PlotSerializer,
)

logger = logging.getLogger(__name__)

RAG_TOP_K = 4

_GENERAL_QUERY_TOKENS = frozenset({
    'general', 'todos', 'todo', 'historial', 'historial completo',
    'resumen general', 'todos los analisis', 'todos los análisis',
    'todos mis resultados', 'all results', 'general info',
    'informacion general', 'información general', 'todas las plantas',
    'todos los diagnosticos', 'todos los diagnósticos',
    'panorama general', 'vision general', 'visión general',
})


def _is_general_query(message: str, farm_context: str) -> bool:
    """ Detecta si el mensaje pide info general SIN contexto específico. """
    msg_lower = message.lower().strip()
    if farm_context and any(kw in farm_context.lower() for kw in ('síntoma', 'sintoma', 'parte afectada', 'diagnóstico', 'diagnostico', 'planta')):
        return False
    for token in _GENERAL_QUERY_TOKENS:
        if token in msg_lower:
            return True
    return False


_GENERAL_QUERY_RESPONSE = (
    'Para informacion general de todos tus análisis, te recomiendo '
    'visitar la pagina de Historial en la aplicacion. Ahí puedes encontrar '
    'análisis detallados, trazabilidad y evolución de tus plantas. '
    'Si tienes una consulta específica sobre un síntoma, plaga o diagnóstico '
    'particular, estaré encantado de ayudarte.'
)


class FarmViewSet(CurrentUserCreateMixin, viewsets.ModelViewSet):
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Farm.objects.filter(user=self.request.user).prefetch_related('plots')


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


class ConversationViewSet(CurrentUserCreateMixin, viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).prefetch_related('messages').order_by('-updated_at')


class ChatMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ChatMessage.objects.filter(conversation__user=self.request.user).select_related('conversation')

    def perform_create(self, serializer):
        serializer.save()


class PlantHistoryViewSet(OwnerFilterMixin, viewsets.ModelViewSet):
    serializer_class = PlantHistorySerializer
    permission_classes = [IsAuthenticated]
    owner_field = 'context__plot__farm__user'
    queryset = PlantHistory.objects.select_related('context__plot__farm')

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        range_filter = params.get('range', 'all').strip().lower()
        date_from = params.get('date_from', '').strip()
        date_to = params.get('date_to', '').strip()
        return _filter_by_range(qs, range_filter, date_from, date_to)

    def perform_create(self, serializer):
        serializer.save()


class AskChatbotView(APIView):
    """
    Endpoint principal del chatbot con arquitectura RAG.

    Flujo:
      1. Recibe el mensaje del usuario y el ID de conversación.
      2. Carga el contexto agrícola de la conversación (finca, parcela, síntomas…).
      3. Recupera chunks relevantes de la base de conocimiento (RAG semántico).
      4. Construye un prompt enriquecido y lo envía al microservicio Gemma en Colab.
      5. Retorna la respuesta generada por el modelo.

    POST /api/v2/chatbot/chat/
    Body: { "message": "...", "conversation_id": <int|null>, "max_length": 512 }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        message, conversation_id, max_length, no_rag = self._parse_chat_request(request, 1024)

        if not message:
            return Response(
                {'error': 'El campo message es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        farm_context = self._build_farm_context(conversation_id, request.user)

        if _is_general_query(message, farm_context):
            return Response({'response': _GENERAL_QUERY_RESPONSE})

        rag_context = '' if no_rag else _build_rag_context(message)

        full_context = _merge_contexts(farm_context, rag_context)

        logger.info(
            'AskChatbot: conv=%s rag_chunks=%s farm_ctx=%s',
            conversation_id,
            bool(rag_context),
            bool(farm_context),
        )

        ai_response = chatbot_client.chat(
            message=message,
            context=full_context,
            max_length=max_length,
        )

        return Response({'response': ai_response})


    def _parse_chat_request(self, request, default_max_length):
        """Extrae y normaliza los campos comunes del body de /chat y /chat/stream."""
        message = request.data.get('message', '').strip()
        conversation_id = request.data.get('conversation_id')
        try:
            max_length = int(request.data.get('max_length', default_max_length))
        except (TypeError, ValueError):
            max_length = default_max_length
        no_rag = bool(request.data.get('no_rag', False))
        return message, conversation_id, max_length, no_rag

    def _build_farm_context(self, conversation_id, user) -> str:
        """Construye texto con los datos agrícolas de la conversación activa."""
        if not conversation_id:
            return ''
        try:
            conv = (
                Conversation.objects
                .filter(id=conversation_id, user=user)
                .select_related('context__plot__farm')
                .prefetch_related('context__plant_histories')
                .first()
            )
            if not conv or not conv.context:
                return ''

            ctx = conv.context
            parts = []

            if ctx.plot:
                plot = ctx.plot
                parts.append(f'Parcela: {plot.name}')
                if plot.farm:
                    parts.append(f'Finca: {plot.farm.name}')
                    if plot.farm.location:
                        parts.append(f'Ubicación: {plot.farm.location}')
                if plot.zone:
                    parts.append(f'Zona del cultivo: {plot.zone}')
                if plot.hectares:
                    parts.append(f'Superficie: {plot.hectares} ha')
                if plot.rows:
                    parts.append(f'Filas/Identificador: {plot.rows}')
                if plot.gps_location:
                    coords = re.findall(r'-?\d+\.?\d*', plot.gps_location)
                    if len(coords) >= 2:
                        weather_text = get_weather_summary(float(coords[0]), float(coords[1]))
                        if weather_text:
                            parts.append(weather_text)

            if ctx.plant_key_or_id:
                parts.append(f'Identificador de planta: {ctx.plant_key_or_id}')
            if ctx.affected_part:
                parts.append(f'Parte afectada: {ctx.affected_part}')
            if ctx.main_symptom:
                parts.append(f'Síntoma principal observado: {ctx.main_symptom}')
            if ctx.status:
                parts.append(f'Estado de la planta: {ctx.status}')

            latest_history = ctx.plant_histories.order_by('-created_at').first()
            if latest_history:
                if latest_history.final_diagnosis:
                    parts.append(f'Diagnóstico IA previo: {latest_history.final_diagnosis}')
                if latest_history.treatment_applied:
                    parts.append(f'Tratamiento recomendado: {latest_history.treatment_applied}')

            if not parts:
                return ''

            return 'DATOS DEL CULTIVO DEL USUARIO:\n' + '\n'.join(parts)

        except Exception:
            logger.exception('Error construyendo contexto agrícola para conv=%s', conversation_id)
            return ''


class StreamChatbotView(AskChatbotView):
    """
    Versión streaming de AskChatbotView.
    Devuelve SSE (text/event-stream) con tokens a medida que Gemma los genera.

    POST /api/v2/chatbot/chat/stream/
    Body: { "message": "...", "conversation_id": <int|null>, "max_length": 250 }
    """

    def post(self, request):
        message, conversation_id, max_length, no_rag = self._parse_chat_request(request, 250)

        if not message:
            return Response(
                {'error': 'El campo message es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        farm_context = self._build_farm_context(conversation_id, request.user)

        if _is_general_query(message, farm_context):
            def _general_stream():
                import json as _json
                yield b"data: " + _json.dumps({'token': _GENERAL_QUERY_RESPONSE, 'done': False}).encode() + b"\n\n"
                yield b"data: " + _json.dumps({'token': '', 'done': True}).encode() + b"\n\n"
            response = StreamingHttpResponse(_general_stream(), content_type='text/event-stream')
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response

        rag_context = '' if no_rag else _build_rag_context(message)
        full_context = _merge_contexts(farm_context, rag_context)

        def stream():
            try:
                yield from chatbot_client.chat_stream(message, full_context, max_length)
            except Exception:
                import json as _json
                logger.exception('Error en StreamChatbotView')
                yield b"data: " + _json.dumps({'token': 'Error al generar respuesta.', 'done': False}).encode() + b"\n\n"
                yield b"data: " + _json.dumps({'token': '', 'done': True}).encode() + b"\n\n"

        response = StreamingHttpResponse(stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


def _parse_suggestions(raw: str) -> list[str]:
    """Limpia la salida de Gemma y extrae hasta 3 preguntas."""
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    cleaned = []
    for line in lines:
        line = re.sub(r'^[\d]+[.)]\s*', '', line)
        line = re.sub(r'^[-*•]\s*', '', line)
        line = line.strip('"\'')
        if line and len(line) > 8:
            cleaned.append(line)
    return cleaned[:3]


class ExportBackupView(APIView):
    """
    Genera un respaldo con los datos ACTUALES del usuario autenticado.
    - Administradores: incluye los análisis/historiales de TODOS los usuarios.
    - Usuarios normales: incluye únicamente los suyos.
    Admite filtrar por rango de fechas sobre la fecha del análisis.

    GET /api/v2/chatbot/export-backup/?range=today|last7|month&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params
        range_filter = params.get('range', '').strip().lower()
        date_from = params.get('date_from', '').strip()
        date_to = params.get('date_to', '').strip()

        admin = is_admin(request.user)

        analyses_qs = AnalysisResult.objects.select_related(
            'user', 'conversation__context__plot__farm',
        ).prefetch_related('conversation__messages')
        if not admin:
            analyses_qs = analyses_qs.filter(user=request.user)
        analyses_qs = _filter_by_range(analyses_qs, range_filter, date_from, date_to).order_by('-created_at')

        analyses = list(analyses_qs)
        plant_histories_by_ar = {}
        ar_ids = [ar.id for ar in analyses]
        for ph in PlantHistory.objects.filter(analysis_result_id__in=ar_ids):
            plant_histories_by_ar.setdefault(ph.analysis_result_id, ph)

        historiales = [
            self._build_entry(ar, plant_histories_by_ar.get(ar.id), request, admin)
            for ar in analyses
        ]

        profile, _ = Profile.objects.get_or_create(user=request.user)
        settings_payload = {
            'notifications_enabled': profile.notifications_enabled,
            'notify_severity_threshold': profile.notify_severity_threshold,
        }

        payload = {
            'exportedAt': timezone.now().isoformat(),
            'role': 'administrador' if admin else 'usuario',
            'dateFrom': date_from or None,
            'dateTo': date_to or None,
            'totalRegistros': len(historiales),
            'data': {
                'pitahayaVision.plantHistory.v1': historiales,
                'pitahayaVision.settings.v1': settings_payload,
            },
        }
        return Response(payload)

    @staticmethod
    def _build_entry(ar, plant_history, request, admin):
        ar_data = AnalysisResultSerializer(ar, context={'request': request}).data
        conv = ar.conversation
        ctx = conv.context if conv else None
        plot = ctx.plot if ctx and ctx.plot_id else None
        farm = plot.farm if plot and plot.farm_id else None

        context_detail = None
        if ctx:
            context_detail = {
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
                'hectares': plot.hectares if plot else None,
                'location': plot.gps_location if plot else '',
                'created_at': ctx.created_at.isoformat() if ctx.created_at else '',
            }

        messages = []
        if conv:
            messages = [
                {
                    'role': m.role,
                    'content': m.content,
                    'image_type': m.image_type,
                    'image_path': m.image_path,
                    'created_at': m.created_at.isoformat(),
                }
                for m in sorted(conv.messages.all(), key=lambda m: m.created_at)
            ]

        entry = {
            'id': ar.id,
            'plant_key': f'{ctx.plant_key_or_id}|{ctx.plot_id}' if ctx else '',
            'created_at': ar_data['created_at'],
            'title': conv.title if conv else '',
            'final_diagnosis': (plant_history.final_diagnosis if plant_history else '') or ar_data['disease_name_predicted'],
            'disease_name_predicted': ar_data['disease_name_predicted'],
            'treatment_applied': (plant_history.treatment_applied if plant_history else '') or ar_data['recommendations_text'],
            'recommendations_text': ar_data['recommendations_text'],
            'notes': (plant_history.notes if plant_history else '') or ar_data['analysis_text'],
            'analysis_text': ar_data['analysis_text'],
            'severity': ar_data['severity'],
            'confidence_percent': ar_data['confidence_percent'],
            'probability': ar_data['probability'],
            'latitude': ar_data['latitude'],
            'longitude': ar_data['longitude'],
            'image_url': ar_data['image_url'],
            'context_detail': context_detail,
            'messages': messages,
        }
        if admin:
            entry['owner_name'] = ar_data['owner_name']
            entry['owner_email'] = ar_data['owner_email']
        return entry


def _fetch_image_content(image_url, request):
    """
    Recupera los bytes de una imagen de análisis a partir de su URL, siempre que
    viva en el MEDIA_ROOT de este mismo servidor (caso normal: exportar e importar
    dentro del mismo despliegue). No se hacen fetches HTTP a hosts externos para
    evitar SSRF con URLs arbitrarias provistas por el archivo de respaldo.
    Devuelve (contenido_bytes, nombre_archivo) o (None, None) si no se pudo obtener.
    """
    parsed = urlparse(image_url)
    media_url_path = urlparse(settings.MEDIA_URL).path if settings.MEDIA_URL else '/media/'
    same_host = not parsed.netloc or parsed.netloc == request.get_host()
    if not same_host or media_url_path not in parsed.path:
        return None, None

    rel_path = unquote(parsed.path.split(media_url_path, 1)[-1].lstrip('/'))
    media_root = os.path.abspath(str(settings.MEDIA_ROOT))
    abs_path = os.path.abspath(os.path.join(media_root, rel_path))
    if abs_path != media_root and not abs_path.startswith(media_root + os.sep):
        return None, None
    if not os.path.isfile(abs_path):
        return None, None

    with open(abs_path, 'rb') as fh:
        return fh.read(), os.path.basename(abs_path)


@transaction.atomic
def _import_plant_history_record(request, hist, idx, resultados):
    """
    Importa un registro de historial de planta (finca/parcela/contexto +
    conversación + análisis). Todo o nada: si algo falla a mitad de camino,
    las filas ya creadas para ESTE registro se revierten en vez de quedar
    huérfanas (los registros ya importados antes de este no se ven afectados).
    """
    cd = hist.get('context_detail') or {}
    farm_name = normalize_name((cd.get('farm_name') or cd.get('lotId') or '').strip())
    plot_name = normalize_name((cd.get('plot_name') or '').strip())
    location = (cd.get('location') or '').strip()

    if not farm_name or not plot_name:
        resultados['saltados'] += 1
        return

    farm, _ = Farm.objects.get_or_create(
        user=request.user,
        name=farm_name,
        defaults={'location': location},
    )

    plot, _ = Plot.objects.get_or_create(
        farm=farm,
        name=plot_name,
        defaults={
            'zone': (cd.get('zone') or '').strip(),
            'rows': str(cd.get('rows') or ''),
            'hectares': float(cd.get('hectares') or 0.0),
            'gps_location': location,
        },
    )

    plant_key = normalize_name((cd.get('plant_key_or_id') or '').strip())
    ctx, _ = Context.objects.get_or_create(
        plot=plot,
        plant_key_or_id=plant_key,
        defaults={
            'affected_part': (cd.get('affected_part') or '').strip(),
            'main_symptom': (cd.get('main_symptom') or '').strip(),
            'status': (cd.get('status') or cd.get('severity') or 'desconocida').strip().lower(),
        },
    )

    messages = hist.get('messages') or []
    conv = None
    if messages:
        conv = Conversation.objects.create(
            user=request.user,
            context=ctx,
            title=(
                hist.get('title')
                or f'{plant_key or plot_name} — {messages[0].get("created_at", "")[:10]}'
            ),
        )
        for msg in messages:
            ChatMessage.objects.create(
                conversation=conv,
                role=msg.get('role', 'user'),
                content=msg.get('content', ''),
                image_type=msg.get('image_type', ''),
                image_path=msg.get('image_path', ''),
            )
        resultados['sesiones'] += 1

    analysis = None
    if hist.get('disease_name_predicted') or hist.get('severity') or hist.get('image_url'):
        confidence_percent = hist.get('confidence_percent') or 0
        analysis = AnalysisResult.objects.create(
            user=request.user,
            conversation=conv,
            disease_name_predicted=(hist.get('disease_name_predicted') or hist.get('final_diagnosis') or ''),
            confidence=float(confidence_percent) / 100.0,
            probability=float(hist.get('probability') or 0.0),
            severity=(hist.get('severity') or cd.get('status') or 'desconocida'),
            analysis_text=(hist.get('analysis_text') or hist.get('notes') or ''),
            recommendations_text=(hist.get('recommendations_text') or hist.get('treatment_applied') or ''),
            latitude=hist.get('latitude'),
            longitude=hist.get('longitude'),
        )
        if hist.get('created_at'):
            AnalysisResult.objects.filter(pk=analysis.pk).update(created_at=hist['created_at'])

        image_url = hist.get('image_url')
        if image_url:
            try:
                content, filename = _fetch_image_content(image_url, request)
                if content:
                    analysis.image_path.save(filename, ContentFile(content), save=False)
                    analysis.save(update_fields=['image_path'])
                    resultados['imagenes'] += 1
                else:
                    resultados['errores'].append(f'#{idx}: imagen no encontrada en el origen')
            except Exception as e:
                logger.exception('Error descargando imagen del historial #%d', idx)
                resultados['errores'].append(f'#{idx}: no se pudo descargar la imagen ({e})')

    ph = PlantHistory.objects.create(
        context=ctx,
        analysis_result=analysis,
        final_diagnosis=(hist.get('final_diagnosis') or hist.get('disease_name_predicted') or ''),
        treatment_applied=(hist.get('treatment_applied') or hist.get('recommendations_text') or ''),
        notes=(hist.get('notes') or hist.get('analysis_text') or ''),
    )
    if hist.get('created_at'):
        PlantHistory.objects.filter(pk=ph.pk).update(created_at=hist['created_at'])
    resultados['historiales'] += 1


class ImportBackupView(APIView):
    """
    Importa un respaldo completo de plant histories, sesiones, análisis (con imagen) y settings.
    POST /api/v2/chatbot/import-backup/
    Body: { "data": { "pitahayaVision.plantHistory.v1": [...], "pitahayaVision.settings.v1": {...} } }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data.get('data', {})
        if not isinstance(data, dict):
            return Response({'error': 'data debe ser un objeto'}, status=status.HTTP_400_BAD_REQUEST)

        resultados = {'settings': False, 'sesiones': 0, 'historiales': 0, 'imagenes': 0, 'saltados': 0, 'errores': []}

        settings_data = data.get('pitahayaVision.settings.v1')
        if settings_data and isinstance(settings_data, dict):
            try:
                profile, _ = Profile.objects.get_or_create(user=request.user)
                for field in ('notifications_enabled', 'notify_severity_threshold'):
                    if field in settings_data:
                        setattr(profile, field, settings_data[field])
                profile.save()
                resultados['settings'] = True
            except Exception as e:
                logger.exception('Error importando settings')
                resultados['errores'].append(f'Settings: {e}')

        historiales = data.get('pitahayaVision.plantHistory.v1', [])
        logger.info('Importando %d historiales de planta…', len(historiales))

        for idx, hist in enumerate(historiales):
            try:
                _import_plant_history_record(request, hist, idx, resultados)
            except Exception as e:
                logger.exception('Error en historial #%d', idx)
                resultados['errores'].append(
                    f'#{idx} (plant_key={hist.get("plant_key", "?")}): {e}'
                )

        logger.info(
            'Import completado: %d historiales, %d sesiones, %d errores',
            resultados['historiales'], resultados['sesiones'], len(resultados['errores']),
        )
        return Response(resultados, status=status.HTTP_200_OK)


class SuggestQuestionsView(APIView):
    """
    Genera 3 preguntas de seguimiento basadas en el conjunto de respuestas
    generadas para el análisis actual (diagnóstico del modelo, explicación de
    Gemma, plan de tratamiento y comparación con análisis previo si existe).
    NO usa RAG ni contexto agrícola — solo Gemma interpreta el texto recibido.

    POST /api/v2/chatbot/suggest/
    Body: { "bot_response": "..." }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        bot_response = request.data.get('bot_response', '').strip()
        if not bot_response or len(bot_response) < 20:
            return Response({'suggestions': []})

        prompt = (
            'Basándote en la siguiente información sobre un análisis de pitahaya '
            '(puede incluir diagnóstico, explicación, plan de tratamiento y '
            'comparación con un análisis previo):\n\n'
            f'"""\n{bot_response[:1600]}\n"""\n\n'
            'Genera exactamente 3 preguntas cortas (máximo 10 palabras cada una) '
            'que el agricultor podría querer preguntar a continuación.\n'
            'IMPORTANTE: Responde ÚNICAMENTE con las 3 preguntas, una por línea, '
            'sin numeración, sin viñetas, sin texto adicional.'
        )

        try:
            raw = chatbot_client.chat(message=prompt, context='', max_length=180)
            suggestions = _parse_suggestions(raw)
        except Exception:
            logger.warning('Gemma no disponible para sugerencias; retornando lista vacía.')
            return Response({'suggestions': []})

        logger.info('Sugerencias generadas: %s', suggestions)
        return Response({'suggestions': suggestions})


class HeatmapAnalysisView(APIView):
    """
    Genera un análisis agrónomo del mapa de calor usando Gemma 3.

    POST /api/v2/chatbot/heatmap-analysis/
    Body: { "summary": "resumen en texto de los datos del mapa" }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        summary = request.data.get('summary', '').strip()
        if not summary:
            return Response({'error': 'summary es requerido'}, status=status.HTTP_400_BAD_REQUEST)

        prompt = (
            'Eres un agrónomo experto en cultivos de pitahaya. '
            'Analiza los siguientes datos del mapa de calor de detección de enfermedades en la finca.\n\n'
            'FORMATO OBLIGATORIO — usa exactamente estos encabezados markdown:\n'
            '## Diagnóstico general\n'
            '<párrafo con el estado fitosanitario general>\n\n'
            '## Zonas de riesgo\n'
            '<lista con guiones de patrones o zonas detectadas>\n\n'
            '## Recomendaciones\n'
            '<lista con guiones de acciones concretas preventivas y correctivas>\n\n'
            'Sé conciso y profesional. No agregues secciones adicionales.\n\n'
            f'DATOS DEL MAPA DE CALOR:\n{summary}'
        )

        try:
            analysis = chatbot_client.chat(message=prompt, context='', max_length=600)
        except Exception:
            logger.exception('Error generando el análisis del mapa de calor')
            return Response(
                {'error': 'No se pudo generar el análisis en este momento.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'analysis': analysis})


def _build_rag_context(query: str) -> str:
    """Recupera los chunks más relevantes de la base de conocimiento RAG."""
    try:
        from apps.rag.retriever import build_rag_context
        return build_rag_context(query, top_k=RAG_TOP_K)
    except Exception:
        logger.warning('RAG no disponible para "%s..." — sin RAG', query[:60])
        return ''


def _merge_contexts(farm_context: str, rag_context: str) -> str:
    """Combina el contexto agrícola y el RAG en un único bloque para Gemma."""
    parts = [p for p in [farm_context, rag_context] if p.strip()]
    return '\n\n'.join(parts)
