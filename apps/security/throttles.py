from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'

    def get_rate(self):
        return getattr(settings, 'LOGIN_THROTTLE_RATE', '3/minute')


class RegisterRateThrottle(AnonRateThrottle):
    scope = 'register'


class PasswordResetRateThrottle(AnonRateThrottle):
    scope = 'password_reset'


class EmailVerificationRateThrottle(AnonRateThrottle):
    scope = 'email_verification'


class AvailabilityRateThrottle(AnonRateThrottle):
    scope = 'availability'


class AuthenticatedUserThrottle(UserRateThrottle):
    scope = 'authenticated_user'
