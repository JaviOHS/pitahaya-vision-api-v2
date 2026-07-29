import json as _json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

from .client import predict as analysis_predict

logger = logging.getLogger(__name__)


def classify_leaf(image_file) -> dict:
    return analysis_predict(image_file)


def get_weather_summary(lat: float, lon: float, days: int = 3) -> str:
    """Resumen breve del clima reciente de una ubicación, para usar como contexto textual del chatbot."""
    cache_key = f'weather_summary_{lat}_{lon}_{days}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    api_keys = [k for k in (settings.VISUAL_CROSSING_API_KEY, settings.VISUAL_CROSSING_API_KEY_BACKUP) if k]
    if not api_keys:
        return ''

    params = urllib.parse.urlencode({
        'unitGroup': 'metric', 'key': api_keys[0], 'include': 'days',
        'elements': 'precip,humidity,temp', 'contentType': 'json',
    })
    url = f'https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/last{days}days?{params}'

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            days_data = _json.loads(resp.read().decode()).get('days', [])
    except Exception as e:
        logger.warning('No se pudo obtener clima para contexto del chatbot: %s', e)
        return ''

    if not days_data:
        return ''

    avg_temp = sum(d.get('temp') or 0 for d in days_data) / len(days_data)
    avg_humidity = sum(d.get('humidity') or 0 for d in days_data) / len(days_data)
    total_precip = sum(d.get('precip') or 0 for d in days_data)

    summary = (
        f'Clima reciente en la parcela (últimos {days} días): '
        f'temperatura promedio {avg_temp:.1f}°C, humedad relativa promedio {avg_humidity:.0f}%, '
        f'precipitación acumulada {total_precip:.1f}mm.'
    )
    cache.set(cache_key, summary, 60 * 60)
    return summary
