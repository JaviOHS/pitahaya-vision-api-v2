import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SERVICE_URL = getattr(settings, 'CHATBOT_SERVICE_URL', '').rstrip('/')
TIMEOUT = getattr(settings, 'CHATBOT_SERVICE_TIMEOUT', 120)

_NGROK_HEADERS = {'ngrok-skip-browser-warning': 'true'}


class ChatbotClientError(Exception):
    pass


def chat(message: str, context: str = '', max_length: int = 384) -> str:
    if not SERVICE_URL:
        logger.warning('CHATBOT_SERVICE_URL no configurada en settings')
        return 'El servicio de chatbot no está configurado. Contacta al administrador.'

    url = f'{SERVICE_URL}/chat'
    try:
        response = requests.post(
            url,
            json={'message': message, 'context': context, 'max_length': max_length},
            headers=_NGROK_HEADERS,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data.get('response', 'Sin respuesta del modelo.')
    except requests.exceptions.Timeout:
        logger.warning('Timeout al llamar chatbot service (%ss)', TIMEOUT)
        return 'El asistente tardó demasiado en responder. Intenta de nuevo.'
    except requests.exceptions.ConnectionError as exc:
        logger.warning('Error de conexión al chatbot service: %s', exc)
        return 'No se pudo conectar con el asistente de IA. Verifica que el servicio esté activo.'
    except requests.exceptions.RequestException as exc:
        logger.exception('Error HTTP en chatbot service: %s', exc)
        return 'Ocurrió un error al consultar el asistente.'


def health() -> dict:
    if not SERVICE_URL:
        return {'status': 'not_configured'}
    try:
        response = requests.get(
            f'{SERVICE_URL}/health',
            headers=_NGROK_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        logger.warning('Health check del chatbot falló: %s', exc)
        return {'status': 'unreachable', 'error': str(exc)}
