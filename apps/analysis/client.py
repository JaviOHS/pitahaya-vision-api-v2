import logging
import time
from io import BytesIO

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SERVICE_URL = settings.ANALYSIS_SERVICE_URL.rstrip('/')
TIMEOUT = settings.ANALYSIS_SERVICE_TIMEOUT
MAX_RETRIES = 3
BASE_BACKOFF = 1.0


def _build_fallback(message: str = '') -> dict:
    return {
        'status': 'enferma',
        'disease_name': 'Pendiente de revisión',
        'confidence': 0.0,
        'recommendation': (
            'No se pudo conectar con el servicio de análisis automático. '
            f'{message} Solicita revisión técnica de la imagen.'
        ),
    }


def predict(image_file) -> dict:
    url = f'{SERVICE_URL}/predict'
    file_bytes = _read_image_bytes(image_file)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            files = {'file': ('image.jpg', BytesIO(file_bytes), 'image/jpeg')}
            response = requests.post(url, files=files, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            return {
                'status': data.get('status', 'enferma'),
                'disease_name': data.get('disease_name', 'Pendiente de revisión'),
                'confidence': float(data.get('confidence', 0.0) or 0.0),
                'recommendation': data.get('recommendation', ''),
            }
        except requests.exceptions.Timeout:
            message = f'Timeout tras {TIMEOUT}s (intento {attempt}/{MAX_RETRIES}).'
            logger.warning(message)
            if attempt < MAX_RETRIES:
                _sleep_backoff(attempt)
                continue
            return _build_fallback(message)
        except requests.exceptions.ConnectionError:
            message = f'Conexión rechazada en {url} (intento {attempt}/{MAX_RETRIES}).'
            logger.warning(message)
            if attempt < MAX_RETRIES:
                _sleep_backoff(attempt)
                continue
            return _build_fallback(message)
        except requests.exceptions.RequestException as exc:
            message = f'Error HTTP en el servicio de análisis: {exc}'
            logger.exception(message)
            return _build_fallback(message)

    return _build_fallback('Máximo de reintentos alcanzado.')


def health() -> bool:
    try:
        url = f'{SERVICE_URL}/health'
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get('model_loaded', False)
    except requests.exceptions.RequestException as exc:
        logger.warning('Health check falló: %s', exc)
        return False


def _read_image_bytes(image_file) -> bytes:
    if hasattr(image_file, 'seek'):
        image_file.seek(0)
    data = image_file.read()
    if hasattr(image_file, 'seek'):
        image_file.seek(0)
    return data


def _sleep_backoff(attempt: int):
    wait = BASE_BACKOFF * (2 ** (attempt - 1))
    time.sleep(wait)
