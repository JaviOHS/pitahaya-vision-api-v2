from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

TOKEN_EXPIRY_HOURS = getattr(settings, 'TOKEN_EXPIRY_HOURS', 168)


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)

        if token.created < timezone.now() - timedelta(hours=TOKEN_EXPIRY_HOURS):
            token.delete()
            raise AuthenticationFailed(
                'Sesión expirada. Inicia sesión nuevamente.',
            )

        return user, token
