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

    return response
