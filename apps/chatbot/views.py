import logging
import re

from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.security.models import Profile
from apps.security.mixins import CurrentUserCreateMixin, OwnerFilterMixin

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

# Número de chunks RAG a inyectar en el contexto del modelo
RAG_TOP_K = 4


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
    pagination_class = None
    owner_field = 'context__plot__farm__user'
    queryset = PlantHistory.objects.select_related('context__plot__farm')

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
        message = request.data.get('message', '').strip()
        conversation_id = request.data.get('conversation_id')
        max_length = int(request.data.get('max_length', 1024))
        no_rag = bool(request.data.get('no_rag', False))

        if not message:
            return Response(
                {'error': 'El campo message es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Contexto agrícola desde la conversación guardada en DB
        farm_context = self._build_farm_context(conversation_id, request.user)

        # 2. Contexto RAG (omitido cuando no_rag=True, p.ej. comparaciones)
        rag_context = '' if no_rag else _build_rag_context(message)

        # 3. Combinar contextos en un único bloque coherente para Gemma
        full_context = _merge_contexts(farm_context, rag_context)

        logger.info(
            'AskChatbot: conv=%s rag_chunks=%s farm_ctx=%s',
            conversation_id,
            bool(rag_context),
            bool(farm_context),
        )

        # 4. Llamar al microservicio Gemma (ngrok / Colab)
        ai_response = chatbot_client.chat(
            message=message,
            context=full_context,
            max_length=max_length,
        )

        return Response({'response': ai_response})

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

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
        message = request.data.get('message', '').strip()
        conversation_id = request.data.get('conversation_id')
        max_length = int(request.data.get('max_length', 250))
        no_rag = bool(request.data.get('no_rag', False))

        if not message:
            return Response(
                {'error': 'El campo message es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        farm_context = self._build_farm_context(conversation_id, request.user)
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
        line = re.sub(r'^[\d]+[.)]\s*', '', line)   # quitar "1. "
        line = re.sub(r'^[-*•]\s*', '', line)         # quitar "- "
        line = line.strip('"\'')
        if line and len(line) > 8:
            cleaned.append(line)
    return cleaned[:3]


class ImportBackupView(APIView):
    """
    Importa un respaldo completo de plant histories, sesiones y settings.
    POST /api/v2/chatbot/import-backup/
    Body: { "data": { "pitahayaVision.plantHistory.v1": [...], "pitahayaVision.sessions.v2": [...], "pitahayaVision.settings.v1": {...} } }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data.get('data', {})
        if not isinstance(data, dict):
            return Response({'error': 'data debe ser un objeto'}, status=status.HTTP_400_BAD_REQUEST)

        resultados = {'settings': False, 'sesiones': 0, 'historiales': 0, 'saltados': 0, 'errores': []}

        # ─── 1. Settings ───
        settings = data.get('pitahayaVision.settings.v1')
        if settings and isinstance(settings, dict):
            try:
                profile, _ = Profile.objects.get_or_create(user=request.user)
                for field in ('notifications_enabled', 'notify_severity_threshold'):
                    if field in settings:
                        setattr(profile, field, settings[field])
                profile.save()
                resultados['settings'] = True
            except Exception as e:
                logger.exception('Error importando settings')
                resultados['errores'].append(f'Settings: {e}')

        # ─── 2. Historiales de planta ───
        historiales = data.get('pitahayaVision.plantHistory.v1', [])
        logger.info('Importando %d historiales de planta…', len(historiales))

        for idx, hist in enumerate(historiales):
            try:
                cd = hist.get('context_detail') or {}
                farm_name = (cd.get('farm_name') or cd.get('lotId') or '').strip()
                plot_name = (cd.get('plot_name') or '').strip()
                location = (cd.get('location') or '').strip()

                if not farm_name or not plot_name:
                    resultados['saltados'] += 1
                    continue

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
                        'hectares': 0.0,
                    },
                )

                plant_key = (cd.get('plant_key_or_id') or '').strip()
                ctx, _ = Context.objects.get_or_create(
                    plot=plot,
                    plant_key_or_id=plant_key,
                    defaults={
                        'affected_part': (cd.get('affected_part') or '').strip(),
                        'main_symptom': (cd.get('main_symptom') or '').strip(),
                        'status': (cd.get('status') or cd.get('severity') or 'desconocida').strip().lower(),
                    },
                )

                # ── Conversación si hay mensajes (sin imágenes) ──
                messages = hist.get('messages') or []
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
                            image_type='',
                            image_path='',
                        )
                    resultados['sesiones'] += 1

                # ── PlantHistory ──
                PlantHistory.objects.create(
                    context=ctx,
                    final_diagnosis=(hist.get('final_diagnosis') or hist.get('disease_name_predicted') or ''),
                    treatment_applied=(hist.get('treatment_applied') or hist.get('recommendations_text') or ''),
                    notes=(hist.get('notes') or hist.get('analysis_text') or ''),
                )
                resultados['historiales'] += 1

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
    Genera 3 preguntas de seguimiento basadas en la última respuesta del bot.
    NO usa RAG ni contexto agrícola — solo Gemma interpreta la respuesta.

    POST /api/v2/chatbot/suggest/
    Body: { "bot_response": "..." }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        bot_response = request.data.get('bot_response', '').strip()
        if not bot_response or len(bot_response) < 20:
            return Response({'suggestions': []})

        prompt = (
            'Basándote en la siguiente respuesta sobre pitahaya:\n\n'
            f'"""\n{bot_response[:900]}\n"""\n\n'
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

        analysis = chatbot_client.chat(message=prompt, context='', max_length=600)
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
