import json

import requests
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.analysis.models import AnalysisResult
from apps.security.models import Profile

from .models import ChatMessage, Context, Conversation, Farm, PlantHistory, Plot

User = get_user_model()


def _results(response):
    if isinstance(response.data, dict) and 'results' in response.data:
        return response.data['results']
    if isinstance(response.data, list):
        return response.data
    return []


# =============================================================================
# MODEL TESTS
# =============================================================================

class FarmModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='farm_user', password='Pass1234!',
        )

    def test_crear_farm(self):
        farm = Farm.objects.create(user=self.user, name='Finca Test', location='Quito')
        self.assertEqual(str(farm), 'Finca Test')
        self.assertEqual(farm.user, self.user)


class PlotModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='plot_user', password='Pass1234!')
        self.farm = Farm.objects.create(user=self.user, name='Finca Plot')

    def test_crear_plot(self):
        plot = Plot.objects.create(
            farm=self.farm, name='Parcela A', hectares=2.5,
            zone='Zona 1', gps_location='-0.2, -78.5',
        )
        self.assertIn('Finca Plot', str(plot))
        self.assertEqual(plot.hectares, 2.5)

    def test_plot_relation(self):
        Plot.objects.create(farm=self.farm, name='Parcela 1')
        self.assertEqual(self.farm.plots.count(), 1)


class ContextModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ctx_user', password='Pass1234!')
        self.farm = Farm.objects.create(user=self.user, name='Finca Ctx')
        self.plot = Plot.objects.create(farm=self.farm, name='Parcela Ctx')

    def test_crear_context(self):
        ctx = Context.objects.create(
            plot=self.plot, plant_key_or_id='P001',
            affected_part='hoja', main_symptom='manchas marrones',
            status='enferma',
        )
        self.assertIn('Parcela Ctx', str(ctx))
        self.assertEqual(ctx.plant_key_or_id, 'P001')

    def test_context_relation(self):
        Context.objects.create(plot=self.plot)
        self.assertEqual(self.plot.contexts.count(), 1)


class ConversationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='conv_user', password='Pass1234!')
        self.farm = Farm.objects.create(user=self.user, name='Finca Conv')
        self.plot = Plot.objects.create(farm=self.farm, name='Parcela Conv')
        self.ctx = Context.objects.create(plot=self.plot)

    def test_crear_conversacion(self):
        conv = Conversation.objects.create(
            user=self.user, context=self.ctx, title='Mi consulta',
        )
        self.assertIn('conv_user', str(conv))
        self.assertEqual(conv.title, 'Mi consulta')

    def test_updated_at_actualiza(self):
        conv = Conversation.objects.create(user=self.user)
        old_updated = conv.updated_at
        conv.title = 'Nuevo título'
        conv.save()
        self.assertGreaterEqual(conv.updated_at, old_updated)


class ChatMessageModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='msg_user', password='Pass1234!')
        self.conv = Conversation.objects.create(user=self.user)

    def test_crear_mensaje(self):
        msg = ChatMessage.objects.create(
            conversation=self.conv, role='user', content='Hola',
        )
        self.assertIn('user', str(msg))
        self.assertEqual(msg.content, 'Hola')

    def test_mensajes_orden(self):
        ChatMessage.objects.create(conversation=self.conv, role='user', content='A')
        ChatMessage.objects.create(conversation=self.conv, role='assistant', content='B')
        self.assertEqual(self.conv.messages.count(), 2)


class PlantHistoryModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ph_user', password='Pass1234!')
        self.farm = Farm.objects.create(user=self.user, name='Finca PH')
        self.plot = Plot.objects.create(farm=self.farm, name='Parcela PH')
        self.ctx = Context.objects.create(plot=self.plot)

    def test_crear_plant_history(self):
        ph = PlantHistory.objects.create(
            context=self.ctx,
            final_diagnosis='Antracnosis',
            treatment_applied='Fungicida',
        )
        self.assertEqual(ph.final_diagnosis, 'Antracnosis')

    def test_plant_history_con_analysis(self):
        analysis = AnalysisResult.objects.create(user=self.user)
        ph = PlantHistory.objects.create(
            context=self.ctx,
            analysis_result=analysis,
            final_diagnosis='Roya',
        )
        self.assertEqual(ph.analysis_result, analysis)


# =============================================================================
# VIEW TESTS
# =============================================================================

class ChatbotViewsBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='chatbot_user', password='Pass1234!',
            first_name='Chatbot', last_name='User',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.farm = Farm.objects.create(user=self.user, name='Finca Test')
        self.plot = Plot.objects.create(farm=self.farm, name='Parcela 1', hectares=3.0)
        self.ctx = Context.objects.create(plot=self.plot, plant_key_or_id='P001',
                                           affected_part='hoja', main_symptom='manchas')
        self.conv = Conversation.objects.create(user=self.user, context=self.ctx,
                                                 title='Conversación de prueba')


class FarmViewSetTests(ChatbotViewsBase):
    def test_list_farms(self):
        response = self.client.get('/api/v2/chatbot/farms/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(_results(response)), 1)

    def test_create_farm(self):
        response = self.client.post('/api/v2/chatbot/farms/', {
            'name': 'Nueva Finca', 'location': 'Guayaquil',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'Nueva Finca')

    def test_create_farm_solo_para_si_mismo(self):
        otro = User.objects.create_user(username='otro_farm', password='Pass1234!')
        self.client.force_authenticate(user=otro)
        response = self.client.post('/api/v2/chatbot/farms/', {
            'name': 'Finca de otro',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Farm.objects.filter(user=otro).count(), 1)

    def test_detail_farm(self):
        response = self.client.get(f'/api/v2/chatbot/farms/{self.farm.pk}/')
        self.assertEqual(response.status_code, 200)

    def test_farm_no_autenticado_rechaza(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v2/chatbot/farms/')
        self.assertEqual(response.status_code, 401)


class PlotViewSetTests(ChatbotViewsBase):
    def test_list_plots(self):
        response = self.client.get('/api/v2/chatbot/plots/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(_results(response)), 1)

    def test_create_plot(self):
        response = self.client.post('/api/v2/chatbot/plots/', {
            'farm': self.farm.pk, 'name': 'Parcela B', 'hectares': 5.0,
        }, format='json')
        self.assertEqual(response.status_code, 201)

    def test_plot_no_accede_a_otros(self):
        otro = User.objects.create_user(username='otro_plot', password='Pass1234!')
        otra_farm = Farm.objects.create(user=otro, name='Otra Finca')
        otro_plot = Plot.objects.create(farm=otra_farm, name='Otra Parcela')
        response = self.client.get(f'/api/v2/chatbot/plots/{otro_plot.pk}/')
        self.assertEqual(response.status_code, 404)

    def test_plot_update(self):
        response = self.client.patch(
            f'/api/v2/chatbot/plots/{self.plot.pk}/',
            {'name': 'Parcela Actualizada'}, format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_plot_delete(self):
        response = self.client.delete(f'/api/v2/chatbot/plots/{self.plot.pk}/')
        self.assertEqual(response.status_code, 204)


class ContextViewSetTests(ChatbotViewsBase):
    def test_list_contexts(self):
        response = self.client.get('/api/v2/chatbot/contexts/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(_results(response)), 1)

    def test_create_context(self):
        response = self.client.post('/api/v2/chatbot/contexts/', {
            'plot': self.plot.pk, 'plant_key_or_id': 'P002',
            'main_symptom': 'hojas amarillas',
        }, format='json')
        self.assertEqual(response.status_code, 201)


class ConversationViewSetTests(ChatbotViewsBase):
    def test_list_conversations(self):
        response = self.client.get('/api/v2/chatbot/conversations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(_results(response)), 1)

    def test_create_conversation(self):
        response = self.client.post('/api/v2/chatbot/conversations/', {
            'context': self.ctx.pk, 'title': 'Nueva consulta',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], 'Nueva consulta')

    def test_conversation_solo_propias(self):
        otro = User.objects.create_user(username='otro_conv', password='Pass1234!')
        otra_conv = Conversation.objects.create(user=otro)
        response = self.client.get(f'/api/v2/chatbot/conversations/{otra_conv.pk}/')
        self.assertEqual(response.status_code, 404)


class ChatMessageViewSetTests(ChatbotViewsBase):
    def setUp(self):
        super().setUp()
        self.msg = ChatMessage.objects.create(
            conversation=self.conv, role='user', content='¿Qué tiene mi planta?',
        )

    def test_list_messages(self):
        response = self.client.get('/api/v2/chatbot/messages/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(_results(response)), 1)

    def test_create_message(self):
        response = self.client.post('/api/v2/chatbot/messages/', {
            'conversation': self.conv.pk, 'role': 'user', 'content': 'Nuevo mensaje',
        }, format='json')
        self.assertEqual(response.status_code, 201)


class PlantHistoryViewSetTests(ChatbotViewsBase):
    def setUp(self):
        super().setUp()
        self.ph = PlantHistory.objects.create(
            context=self.ctx, final_diagnosis='Antracnosis',
        )

    def test_list_plant_histories(self):
        response = self.client.get('/api/v2/chatbot/plant-histories/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(_results(response)), 1)

    def test_admin_ve_todos(self):
        otro = User.objects.create_user(username='otro_ph', password='Pass1234!')
        otra_farm = Farm.objects.create(user=otro, name='Otra Finca')
        otro_plot = Plot.objects.create(farm=otra_farm, name='Otra Parcela')
        otro_ctx = Context.objects.create(plot=otro_plot)
        PlantHistory.objects.create(context=otro_ctx, final_diagnosis='Otra')
        response = self.client.get('/api/v2/chatbot/plant-histories/')
        self.assertEqual(len(_results(response)), 1)
        admin = User.objects.create_superuser(
            username='admin_ph', email='admin_ph@test.com', password='Admin1234!',
        )
        self.client.force_authenticate(user=admin)
        response = self.client.get('/api/v2/chatbot/plant-histories/')
        self.assertEqual(len(_results(response)), 2)


class AskChatbotViewTests(ChatbotViewsBase):
    @patch('apps.chatbot.views.chatbot_client.chat')
    def test_ask_simple(self, mock_chat):
        mock_chat.return_value = 'La planta tiene Antracnosis.'
        response = self.client.post('/api/v2/chatbot/chat/', {
            'message': '¿Qué tiene mi planta?',
            'conversation_id': self.conv.pk,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('response', response.data)
        self.assertEqual(response.data['response'], 'La planta tiene Antracnosis.')

    def test_ask_sin_mensaje(self):
        response = self.client.post('/api/v2/chatbot/chat/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)

    def test_ask_no_autenticado(self):
        self.client.force_authenticate(user=None)
        response = self.client.post('/api/v2/chatbot/chat/', {
            'message': 'Hola', 'conversation_id': self.conv.pk,
        }, format='json')
        self.assertEqual(response.status_code, 401)

    @patch('apps.chatbot.views.chatbot_client.chat')
    def test_ask_con_no_rag(self, mock_chat):
        mock_chat.return_value = 'Respuesta sin RAG.'
        response = self.client.post('/api/v2/chatbot/chat/', {
            'message': 'Compara dos opciones',
            'no_rag': True,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        mock_chat.assert_called_once()


class StreamChatbotViewTests(ChatbotViewsBase):
    def test_stream_sin_mensaje(self):
        response = self.client.post('/api/v2/chatbot/chat/stream/', {}, format='json')
        self.assertEqual(response.status_code, 400)

    @patch('apps.chatbot.client.chat_stream')
    def test_stream_responde(self, mock_stream):
        mock_stream.return_value = [
            b"data: " + json.dumps({'token': 'Hola', 'done': False}).encode() + b"\n\n",
            b"data: " + json.dumps({'token': '', 'done': True}).encode() + b"\n\n",
        ]
        response = self.client.post('/api/v2/chatbot/chat/stream/', {
            'message': 'Hola',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/event-stream')


class SuggestQuestionsViewTests(ChatbotViewsBase):
    @patch('apps.chatbot.views.chatbot_client.chat')
    def test_suggest_questions(self, mock_chat):
        mock_chat.return_value = (
            '¿Cómo aplicar fungicida?\n¿Cuándo cosechar?\n¿Qué fertilizante usar?'
        )
        response = self.client.post('/api/v2/chatbot/suggest/', {
            'bot_response': 'La antracnosis se trata con fungicidas.',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('suggestions', response.data)
        self.assertEqual(len(response.data['suggestions']), 3)

    def test_suggest_respuesta_corta(self):
        response = self.client.post('/api/v2/chatbot/suggest/', {
            'bot_response': 'Corto',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['suggestions'], [])


class HeatmapAnalysisViewTests(ChatbotViewsBase):
    @patch('apps.chatbot.views.chatbot_client.chat')
    def test_heatmap_analysis(self, mock_chat):
        mock_chat.return_value = '## Diagnóstico general\nTodo bien.'
        response = self.client.post('/api/v2/chatbot/heatmap-analysis/', {
            'summary': 'Temperatura: 25°C, Humedad: 70%',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('analysis', response.data)

    def test_heatmap_sin_summary(self):
        response = self.client.post('/api/v2/chatbot/heatmap-analysis/', {}, format='json')
        self.assertEqual(response.status_code, 400)


class ImportBackupViewTests(ChatbotViewsBase):
    def test_import_backup_completo(self):
        data = {
            'data': {
                'pitahayaVision.settings.v1': {
                    'notifications_enabled': True,
                    'notify_severity_threshold': 'alta',
                },
                'pitahayaVision.plantHistory.v1': [
                    {
                        'title': 'Mi historial',
                        'context_detail': {
                            'farm_name': 'Finca Import',
                            'plot_name': 'Parcela Import',
                            'plant_key_or_id': 'P001',
                            'main_symptom': 'manchas',
                            'zone': 'Zona A',
                        },
                        'messages': [
                            {'role': 'user', 'content': '¿Qué tiene?',
                             'created_at': '2025-01-01'},
                        ],
                        'final_diagnosis': 'Roya',
                        'treatment_applied': 'Fungicida',
                    },
                ],
            },
        }
        response = self.client.post('/api/v2/chatbot/import-backup/', data, format='json')
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['settings'])
        self.assertEqual(result['historiales'], 1)
        self.assertEqual(result['sesiones'], 1)

    def test_import_backup_sin_data(self):
        response = self.client.post('/api/v2/chatbot/import-backup/',
                                     {'data': {}}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_import_backup_data_no_dict(self):
        response = self.client.post('/api/v2/chatbot/import-backup/',
                                     {'data': 'invalido'}, format='json')
        self.assertEqual(response.status_code, 400)


class ChatbotClientTests(TestCase):
    @patch('apps.chatbot.client.SERVICE_URL', '')
    @patch('apps.chatbot.client.requests.post')
    def test_chat_sin_service_url(self, mock_post):
        from apps.chatbot.client import chat
        result = chat('Hola')
        self.assertIn('no está configurado', result)
        mock_post.assert_not_called()

    @patch('apps.chatbot.client.requests.post')
    def test_chat_exitoso(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'response': 'Respuesta OK'}

        with patch('apps.chatbot.client.SERVICE_URL', 'http://localhost:8002'):
            from apps.chatbot.client import chat
            result = chat('Hola', context='Test context', max_length=256)
            self.assertEqual(result, 'Respuesta OK')

    @patch('apps.chatbot.client.requests.post', side_effect=requests.exceptions.Timeout)
    def test_chat_timeout(self, mock_post):
        with patch('apps.chatbot.client.SERVICE_URL', 'http://localhost:8002'):
            from apps.chatbot.client import chat
            result = chat('Hola')
            self.assertIn('tardó demasiado', result)

    @patch('apps.chatbot.client.requests.post', side_effect=requests.exceptions.ConnectionError)
    def test_chat_connection_error(self, mock_post):
        with patch('apps.chatbot.client.SERVICE_URL', 'http://localhost:8002'):
            from apps.chatbot.client import chat
            result = chat('Hola')
            self.assertIn('No se pudo conectar', result)

    @patch('apps.chatbot.client.requests.get')
    def test_health_ok(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'status': 'ok'}
        with patch('apps.chatbot.client.SERVICE_URL', 'http://localhost:8002'):
            from apps.chatbot.client import health
            self.assertEqual(health()['status'], 'ok')

    def test_health_not_configured(self):
        with patch('apps.chatbot.client.SERVICE_URL', ''):
            from apps.chatbot.client import health
            self.assertEqual(health()['status'], 'not_configured')


# =============================================================================
# SERIALIZER TESTS
# =============================================================================

class PlantHistorySerializerTests(ChatbotViewsBase):
    def setUp(self):
        super().setUp()
        self.ph = PlantHistory.objects.create(
            context=self.ctx, final_diagnosis='Antracnosis',
        )

    def test_plant_key_serializer(self):
        from apps.chatbot.serializers import PlantHistorySerializer
        serializer = PlantHistorySerializer(instance=self.ph)
        self.assertIn('P001', serializer.data['plant_key'])

    def test_context_detail_serializer(self):
        from apps.chatbot.serializers import PlantHistorySerializer
        serializer = PlantHistorySerializer(instance=self.ph)
        cd = serializer.data['context_detail']
        self.assertIsNotNone(cd)
        self.assertEqual(cd['farm_name'], 'Finca Test')
        self.assertEqual(cd['plot_name'], 'Parcela 1')

    def test_severity_desde_analysis(self):
        analysis = AnalysisResult.objects.create(
            user=self.user, severity='critica',
        )
        self.ph.analysis_result = analysis
        self.ph.save()
        from apps.chatbot.serializers import PlantHistorySerializer
        serializer = PlantHistorySerializer(instance=self.ph)
        self.assertEqual(serializer.data['severity'], 'critica')

    def test_severity_desde_context(self):
        self.ctx.status = 'moderada'
        self.ctx.save()
        from apps.chatbot.serializers import PlantHistorySerializer
        serializer = PlantHistorySerializer(instance=self.ph)
        self.assertEqual(serializer.data['severity'], 'moderada')


class ConversationSerializerTests(ChatbotViewsBase):
    def test_messages_incluidos(self):
        ChatMessage.objects.create(conversation=self.conv, role='user', content='Hola')
        ChatMessage.objects.create(conversation=self.conv, role='assistant', content='Adiós')
        from apps.chatbot.serializers import ConversationSerializer
        serializer = ConversationSerializer(instance=self.conv)
        self.assertEqual(len(serializer.data['messages']), 2)


class FarmSerializerTests(ChatbotViewsBase):
    def test_plots_incluidos(self):
        Plot.objects.create(farm=self.farm, name='Parcela Extra')
        from apps.chatbot.serializers import FarmSerializer
        serializer = FarmSerializer(instance=self.farm)
        self.assertEqual(len(serializer.data['plots']), 2)
