from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'


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
