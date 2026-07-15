from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import RegexValidator
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import serializers


dni_validator = RegexValidator(
    regex=r'^\d{10}$',
    message='La cédula debe tener exactamente 10 dígitos.',
)

phone_validator = RegexValidator(
    regex=r'^0\d{9}$',
    message='El teléfono debe tener 10 dígitos y comenzar con 0.',
)


EMAIL_VERIFICATION_TIMEOUT = 86400  # 1 día en segundos


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Token de verificación de correo con expiración de 1 día."""
    key_salt = 'apps.security.utils.EmailVerificationTokenGenerator'

    def _check_timeout(self, ts):
        return (self._num_seconds(self._now()) - ts) <= EMAIL_VERIFICATION_TIMEOUT


email_verification_token_generator = EmailVerificationTokenGenerator()


def _validate_password_strength(value):
    try:
        validate_password(value)
    except Exception as exc:
        messages = getattr(exc, 'messages', None) or [str(exc)]
        raise serializers.ValidationError(messages) from exc
    return value


def validate_ecuadorian_dni(value):
    value = (value or '').strip()
    if not value:
        return value
    if not value.isdigit() or len(value) != 10:
        raise serializers.ValidationError('La cédula debe tener exactamente 10 dígitos.')

    province = int(value[:2])
    if province < 1 or province > 24:
        raise serializers.ValidationError('Cédula inválida: provincia no reconocida.')

    # Nota: la restricción de "tercer dígito menor a 6" no es una regla oficial
    # del Registro Civil (no consta en ningún instructivo, reglamento o ley);
    # el único mecanismo de validación formalmente aceptado es el dígito
    # verificador (algoritmo Módulo 10) calculado a continuación.
    coefficients = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for i in range(9):
        product = int(value[i]) * coefficients[i]
        total += product - 9 if product >= 10 else product

    remainder = total % 10
    verifier = 0 if remainder == 0 else 10 - remainder

    if verifier != int(value[9]):
        raise serializers.ValidationError('Cédula inválida: dígito verificador incorrecto.')

    return value


def validate_ecuadorian_phone(value):
    value = (value or '').strip().replace(' ', '').replace('-', '')
    if not value:
        return value
    if not value.isdigit():
        raise serializers.ValidationError('El teléfono solo debe contener dígitos.')
    if len(value) != 10:
        raise serializers.ValidationError('El teléfono debe tener 10 dígitos (ej: 0991234567).')
    if not value.startswith('0'):
        raise serializers.ValidationError('El teléfono debe comenzar con 0.')
    return value


def _resolve_role(user):
    return 'admin' if (user.is_staff or user.is_superuser) else 'usuario'


def _resolve_role_label(user):
    return 'Administrador' if (user.is_staff or user.is_superuser) else 'Usuario'


def _send_html_email(subject_template, body_text_template, body_html_template, context, to_email):
    subject = render_to_string(subject_template, context).strip()
    text_body = render_to_string(body_text_template, context)
    html_body = render_to_string(body_html_template, context)
    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    msg.attach_alternative(html_body, 'text/html')
    msg.send(fail_silently=True)


def notifications_enabled_for(user):
    """Preferencia maestra de notificaciones (Configuraciones > Notificaciones)."""
    profile = getattr(user, 'profile', None)
    return profile is None or profile.notifications_enabled


def send_notification_email(user, subject, heading, message, details=None):
    """Envía un correo de notificación genérico (mismo estilo que el de
    verificación de cuenta), respetando la preferencia notifications_enabled.
    No usarlo directamente para análisis: para eso ver
    apps.analysis.notifications.notify_analysis_result, que además filtra
    por el umbral de severidad elegido por el usuario.

    `details` (opcional): lista de dicts {'label', 'value', 'url' (opcional)}
    que se muestran como una lista de datos adicionales bajo el mensaje
    principal (ej. ubicación, finca, parcela, fecha del análisis).
    """
    if not user or not user.email or not notifications_enabled_for(user):
        return

    context = {
        'user': user,
        'heading': heading,
        'message': message,
        'details': details or [],
        'frontend_url': settings.FRONTEND_URL,
    }
    text_body = render_to_string('notification_email.txt', context)
    html_body = render_to_string('notification_email.html', context)
    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
    msg.attach_alternative(html_body, 'text/html')
    msg.send(fail_silently=True)


def notify_admins(subject, heading, message, details=None, exclude_user=None):
    """Envía el mismo correo de notificación a todos los administradores
    (cada uno respeta su propia preferencia notifications_enabled).
    `exclude_user`: opcional, para no notificar al propio admin cuando él es
    quien generó el evento (ej. su propio análisis crítico)."""
    from .permissions import get_admin_users
    admins = get_admin_users()
    if exclude_user is not None:
        admins = admins.exclude(pk=exclude_user.pk)
    for admin in admins:
        send_notification_email(admin, subject, heading, message, details=details)


def send_verification_email(user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token_generator.make_token(user)
    verification_url = f'{settings.EMAIL_VERIFICATION_FRONTEND_URL}?uid={uidb64}&token={token}'

    context = {
        'user': user,
        'verification_url': verification_url,
        'frontend_url': settings.FRONTEND_URL,
    }

    _send_html_email(
        subject_template='email_verification_subject.txt',
        body_text_template='email_verification.txt',
        body_html_template='email_verification.html',
        context=context,
        to_email=user.email,
    )


def record_login_attempt(user=None, username='', ip_address=None, user_agent='', successful=False):
    from .models import LoginAttempt
    LoginAttempt.objects.create(
        user=user,
        username=username,
        ip_address=ip_address,
        user_agent=user_agent,
        successful=successful,
    )

    if not successful and user:
        lockout_minutes = settings.LOGIN_LOCKOUT_MINUTES
        max_attempts = settings.MAX_LOGIN_ATTEMPTS
        cutoff = timezone.now() - timedelta(minutes=lockout_minutes)
        recent_failures = LoginAttempt.objects.filter(
            user=user,
            successful=False,
            timestamp__gte=cutoff,
        ).count()
        if recent_failures >= max_attempts:
            already_locked = user.account_locked_until and timezone.now() < user.account_locked_until
            if not already_locked:
                user.account_locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
                user.save(update_fields=['account_locked_until'])


class PasswordHistoryValidator:
    def validate(self, password, user=None):
        if user and user.pk:
            from .models import PasswordHistory
            history_entries = PasswordHistory.objects.filter(
                user=user,
            ).order_by('-created_at')[:5]
            from django.contrib.auth.hashers import check_password
            for entry in history_entries:
                if check_password(password, entry.password_hash):
                    raise ValidationError(
                        'Esta contraseña ya fue utilizada anteriormente. Elige una diferente.',
                    )

    def get_help_text(self):
        return 'La contraseña no debe haber sido utilizada anteriormente.'
