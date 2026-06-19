import logging
import re

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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

            if not parts:
                return ''

            return 'DATOS DEL CULTIVO DEL USUARIO:\n' + '\n'.join(parts)

        except Exception:
            logger.exception('Error construyendo contexto agrícola para conv=%s', conversation_id)
            return ''


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

        raw = chatbot_client.chat(message=prompt, context='', max_length=180)
        suggestions = _parse_suggestions(raw)

        logger.info('Sugerencias generadas: %s', suggestions)
        return Response({'suggestions': suggestions})


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
