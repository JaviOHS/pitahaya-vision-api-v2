import io
import json
from unittest.mock import ANY, MagicMock, patch

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.security.models import Profile

from .models import AnalysisResult
from .serializers import AnalysisResultSerializer

User = get_user_model()


def _create_test_image():
    return SimpleUploadedFile(
        name='test.jpg',
        content=(
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01'
            b'\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07'
            b'\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13'
            b'\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c'
            b'\' /5-\'1\x1a\x1c(\'99+,\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\xff\xc0\x00\x0b\x08\x00\x01'
            b'\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05'
            b'\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x01'
            b'\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10'
            b'\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00'
            b'\x00\x00\x00\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13'
            b'Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0'
            b'$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJST'
            b'UVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a'
            b'\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6'
            b'\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2'
            b'\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7'
            b'\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1'
            b'\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01'
            b'\x01\x00\x00?\x00\xd9\xc0\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\xff\xd9'
        ),
        content_type='image/jpeg',
    )


def _create_large_image():
    return SimpleUploadedFile(
        name='large.jpg',
        content=b'a' * (11 * 1024 * 1024),
        content_type='image/jpeg',
    )


class AnalysisResultModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='model_test', password='Pass1234!',
            first_name='Test', last_name='User',
        )

    def test_crear_analysis_result(self):
        analysis = AnalysisResult.objects.create(
            user=self.user,
            disease_name_predicted='Antracnosis',
            confidence=0.95,
            severity='alta',
        )
        self.assertIn('Antracnosis', str(analysis))
        self.assertIsNotNone(analysis.created_at)
        self.assertEqual(analysis.disease_name_predicted, 'Antracnosis')

    def test_ordering_descendente(self):
        a1 = AnalysisResult.objects.create(user=self.user, severity='baja')
        a2 = AnalysisResult.objects.create(user=self.user, severity='alta')
        qs = AnalysisResult.objects.all()
        self.assertEqual(qs.first(), a2)
        self.assertEqual(qs.last(), a1)

    def test_campos_default(self):
        analysis = AnalysisResult.objects.create(user=self.user)
        self.assertEqual(analysis.severity, 'desconocida')
        self.assertEqual(analysis.disease_name_predicted, '')
        self.assertEqual(analysis.confidence, 0.0)
        self.assertEqual(analysis.probability, 0.0)


class AnalysisResultSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='serial_test', password='Pass1234!',
            first_name='Serial', last_name='Test',
        )

    def test_validate_conversation_propia(self):
        from apps.chatbot.models import Conversation
        conv = Conversation.objects.create(user=self.user)
        data = {
            'conversation': conv.pk,
            'image_path': _create_test_image(),
        }
        serializer = AnalysisResultSerializer(
            data=data,
            context={'request': MagicMock(user=self.user)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_validate_conversacion_ajena(self):
        from apps.chatbot.models import Conversation
        otro = User.objects.create_user(username='otro', password='Pass1234!')
        conv = Conversation.objects.create(user=otro)
        data = {
            'conversation': conv.pk,
            'image_path': _create_test_image(),
        }
        serializer = AnalysisResultSerializer(
            data=data,
            context={'request': MagicMock(user=self.user)},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('conversation', serializer.errors)

    def test_validate_imagen_requerida(self):
        serializer = AnalysisResultSerializer(
            data={},
            context={'request': MagicMock(user=self.user)},
        )
        self.assertFalse(serializer.is_valid())

    def test_validate_imagen_demasiado_grande(self):
        data = {'image_path': _create_large_image()}
        serializer = AnalysisResultSerializer(
            data=data,
            context={'request': MagicMock(user=self.user)},
        )
        self.assertFalse(serializer.is_valid())

    def test_get_confidence_percent_normalizado(self):
        analysis = AnalysisResult.objects.create(user=self.user, confidence=0.85)
        serializer = AnalysisResultSerializer(instance=analysis)
        self.assertEqual(serializer.data['confidence_percent'], 85.0)

    def test_get_confidence_percent_ya_en_porcentaje(self):
        analysis = AnalysisResult.objects.create(user=self.user, confidence=95.0)
        serializer = AnalysisResultSerializer(instance=analysis)
        self.assertEqual(serializer.data['confidence_percent'], 95.0)

    def test_get_owner_name_y_email(self):
        analysis = AnalysisResult.objects.create(user=self.user)
        serializer = AnalysisResultSerializer(instance=analysis)
        self.assertEqual(serializer.data['owner_name'], self.user.full_name)
        self.assertEqual(serializer.data['owner_email'], self.user.email)

    def test_get_owner_name_sin_user(self):
        analysis = AnalysisResult.objects.create()
        serializer = AnalysisResultSerializer(instance=analysis)
        self.assertEqual(serializer.data['owner_name'], '')
        self.assertEqual(serializer.data['owner_email'], '')


class AnalysisViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='view_test', password='Pass1234!',
            first_name='View', last_name='Test',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.list_url = '/api/v2/analysis/'

    def _create_analysis(self, user=None, **kwargs):
        defaults = {'disease_name_predicted': 'Roya', 'severity': 'media', 'confidence': 0.78}
        defaults.update(kwargs)
        return AnalysisResult.objects.create(
            user=user or self.user, **defaults,
        )

    def _results(self, response):
        if isinstance(response.data, dict) and 'results' in response.data:
            return response.data['results']
        if isinstance(response.data, list):
            return response.data
        return []

    def test_list_analisis_propios(self):
        self._create_analysis()
        self._create_analysis(disease_name_predicted='Otra')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self._results(response)), 2)

    def test_list_solo_analisis_propios(self):
        otro = User.objects.create_user(username='otro', password='Pass1234!')
        self._create_analysis()
        self._create_analysis(user=otro)
        response = self.client.get(self.list_url, {'page': 1, 'page_size': 50})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self._results(response)), 1)

    def test_list_admin_ve_todos(self):
        admin = User.objects.create_superuser(
            username='admin_analysis', email='admin_analysis@test.com', password='Admin1234!',
        )
        self.client.force_authenticate(user=admin)
        self._create_analysis()
        self._create_analysis(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self._results(response)), 2)

    def test_filtro_range_today(self):
        self._create_analysis()
        response = self.client.get(self.list_url, {'range': 'today'})
        self.assertEqual(response.status_code, 200)

    def test_filtro_por_nombre_admin(self):
        admin = User.objects.create_superuser(
            username='admin3', email='admin3@test.com', password='Admin1234!',
        )
        self.client.force_authenticate(user=admin)
        self._create_analysis(user=self.user)
        response = self.client.get(self.list_url, {'user_name': 'View'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self._results(response)), 1)

    def test_crear_analisis_sin_imagen_falla(self):
        response = self.client.post(self.list_url, {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_detalle_analisis(self):
        analysis = self._create_analysis()
        url = f'{self.list_url}{analysis.pk}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['disease_name_predicted'], 'Roya')

    def test_detalle_analisis_ajeno_no_acceso(self):
        otro = User.objects.create_user(username='otro2', password='Pass1234!')
        analysis = self._create_analysis(user=otro)
        url = f'{self.list_url}{analysis.pk}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_eliminar_analisis(self):
        analysis = self._create_analysis()
        url = f'{self.list_url}{analysis.pk}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AnalysisResult.objects.filter(pk=analysis.pk).exists())


class WeatherProxyViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='weather_test', password='Pass1234!',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v2/analysis/weather/'

    def test_weather_sin_lat_lon(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)

    @override_settings(VISUAL_CROSSING_API_KEY='', VISUAL_CROSSING_API_KEY_BACKUP='')
    def test_weather_sin_api_key(self):
        response = self.client.get(self.url, {'lat': '-0.2', 'lon': '-78.5'})
        self.assertEqual(response.status_code, 503)

    @override_settings(VISUAL_CROSSING_API_KEY='test_key_123')
    @patch('urllib.request.urlopen')
    def test_weather_exitoso(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'days': [
                {'datetime': '2025-01-01', 'temp': 22.0, 'tempmin': 18.0, 'tempmax': 28.0,
                 'precip': 2.0, 'humidity': 65.0, 'windspeed': 10.0},
                {'datetime': '2025-01-02', 'temp': 24.0, 'tempmin': 20.0, 'tempmax': 30.0,
                 'precip': 5.0, 'humidity': 70.0, 'windspeed': 12.0},
            ]
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        response = self.client.get(self.url, {'lat': '-0.2', 'lon': '-78.5', 'days': '3'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('condition', data)
        self.assertIn('days', data)
        self.assertEqual(len(data['days']), 2)

    @override_settings(VISUAL_CROSSING_API_KEY='test_key_123')
    @patch('urllib.request.urlopen', side_effect=Exception('Connection error'))
    def test_weather_error_red(self, mock_urlopen):
        response = self.client.get(self.url, {'lat': '-0.2', 'lon': '-78.5'})
        self.assertEqual(response.status_code, 502)

    def test_weather_no_autenticado(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url, {'lat': '-0.2', 'lon': '-78.5'})
        self.assertEqual(response.status_code, 401)


class AnalysisClientTests(TestCase):
    @patch('apps.analysis.client.requests.post')
    def test_predict_exitoso(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'status': 'enferma',
            'disease_name': 'Antracnosis',
            'confidence': 0.92,
            'recommendation': 'Aplicar fungicida',
        }

        from apps.analysis.client import predict
        image_file = io.BytesIO(b'fake_image_data')
        result = predict(image_file)

        self.assertEqual(result['status'], 'enferma')
        self.assertEqual(result['disease_name'], 'Antracnosis')
        self.assertEqual(result['confidence'], 0.92)
        self.assertEqual(result['recommendation'], 'Aplicar fungicida')

    @patch('apps.analysis.client.requests.post', side_effect=requests.exceptions.ConnectionError)
    def test_predict_fallback_en_error_conexion(self, mock_post):
        from apps.analysis.client import predict
        image_file = io.BytesIO(b'fake_image_data')
        result = predict(image_file)

        self.assertEqual(result['status'], 'enferma')
        self.assertEqual(result['disease_name'], 'Pendiente de revisión')
        self.assertEqual(result['confidence'], 0.0)

    @patch('apps.analysis.client.requests.post', side_effect=requests.exceptions.Timeout)
    def test_predict_fallback_en_timeout(self, mock_post):
        from apps.analysis.client import predict
        image_file = io.BytesIO(b'fake_image_data')
        result = predict(image_file)

        self.assertEqual(result['status'], 'enferma')
        self.assertEqual(result['disease_name'], 'Pendiente de revisión')
        self.assertEqual(result['confidence'], 0.0)

    @patch('apps.analysis.client.requests.get')
    def test_health_ok(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'model_loaded': True}

        from apps.analysis.client import health
        self.assertTrue(health())

    @patch('apps.analysis.client.requests.get', side_effect=requests.exceptions.RequestException)
    def test_health_fail(self, mock_get):
        from apps.analysis.client import health
        self.assertFalse(health())

    def test_read_image_bytes_con_seek(self):
        from apps.analysis.client import _read_image_bytes
        f = io.BytesIO(b'testdata')
        data = _read_image_bytes(f)
        self.assertEqual(data, b'testdata')
        self.assertEqual(f.tell(), 0)

    def test_build_fallback(self):
        from apps.analysis.client import _build_fallback
        result = _build_fallback('custom message')
        self.assertEqual(result['disease_name'], 'Pendiente de revisión')
        self.assertIn('custom message', result['recommendation'])


class AnalysisNotificationsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='notif_test', password='Pass1234!',
            email='notif@test.com',
        )
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.notifications_enabled = True
        profile.save()
        self.analysis = AnalysisResult.objects.create(
            user=self.user,
            severity='alta',
            disease_name_predicted='Antracnosis',
            confidence=0.9,
        )

    @patch('apps.analysis.notifications.send_notification_email')
    def test_notify_analysis_result(self, mock_send):
        from apps.analysis.notifications import notify_analysis_result
        notify_analysis_result(self.analysis)
        mock_send.assert_called_once()

    @patch('apps.analysis.notifications.send_notification_email')
    def test_notify_analysis_notificaciones_desactivadas(self, mock_send):
        self.user.profile.notifications_enabled = False
        self.user.profile.save()
        from apps.analysis.notifications import notify_analysis_result
        notify_analysis_result(self.analysis)
        mock_send.assert_not_called()

    @patch('apps.analysis.notifications.send_notification_email')
    def test_notify_analysis_severity_umbral_no_alcanzado(self, mock_send):
        self.user.profile.notify_severity_threshold = 'critica'
        self.user.profile.save()
        from apps.analysis.notifications import notify_analysis_result
        notify_analysis_result(self.analysis)
        mock_send.assert_not_called()

    @patch('apps.analysis.notifications.send_notification_email')
    def test_notify_admins_of_critical(self, mock_send):
        signal_admin = User.objects.filter(is_superuser=True).first()
        if signal_admin:
            sp, _ = Profile.objects.get_or_create(user=signal_admin)
            sp.notifications_enabled = False
            sp.save()
        admin_user = User.objects.create_superuser(
            username='admin_notif', email='admin_notif@test.com', password='Admin1234!',
        )
        admin_profile, _ = Profile.objects.get_or_create(user=admin_user)
        admin_profile.notifications_enabled = True
        admin_profile.save()
        from apps.analysis.notifications import notify_admins_of_critical_analysis
        notify_admins_of_critical_analysis(self.analysis)
        mock_send.assert_called_once()

    def test_severity_rank_mapping(self):
        from apps.analysis.notifications import SEVERITY_RANK
        self.assertEqual(SEVERITY_RANK['sana'], 0)
        self.assertEqual(SEVERITY_RANK['enferma'], 3)
        self.assertEqual(SEVERITY_RANK['critica'], 4)
