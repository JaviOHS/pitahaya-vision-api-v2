from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import serializers


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

    if int(value[2]) >= 6:
        raise serializers.ValidationError('Cédula inválida: tercer dígito debe ser menor a 6.')

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


def send_verification_email(user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verification_url = f'{settings.EMAIL_VERIFICATION_FRONTEND_URL}?uid={uidb64}&token={token}'

    context = {
        'user': user,
        'verification_url': verification_url,
        'frontend_url': settings.FRONTEND_URL,
    }

    subject = render_to_string('emails/email_verification_subject.txt', context).strip()
    text_body = render_to_string('emails/email_verification.txt', context)
    html_body = render_to_string('emails/email_verification.html', context)

    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
    msg.attach_alternative(html_body, 'text/html')
    msg.send(fail_silently=True)
