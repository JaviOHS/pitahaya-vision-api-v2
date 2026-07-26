from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if isinstance(exc, Throttled) and response is not None:
        wait = exc.wait
        if wait:
            wait = int(wait)
            unidad = 'segundo' if wait == 1 else 'segundos'
            detail = (
                f'Has realizado demasiados intentos. '
                f'Por favor, inténtalo de nuevo en {wait} {unidad}.'
            )
        else:
            detail = 'Has realizado demasiados intentos. Por favor, inténtalo de nuevo más tarde.'
        response.data = {'detail': detail}
        if wait:
            response.data['wait'] = wait

    if response is not None and isinstance(response.data, dict):
        wait = response.data.get('wait')
        if isinstance(wait, list) and len(wait):
            response.data['wait'] = int(wait[0])
        detail = response.data.get('detail')
        if isinstance(detail, list) and len(detail):
            response.data['detail'] = detail[0]

    return response
