from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import LoginSerializer, PasswordResetSerializer

from .models import Profile
from .utils import (
    _resolve_role,
    _resolve_role_label,
    _validate_password_strength,
    record_login_attempt,
    send_verification_email,
    validate_ecuadorian_dni,
    validate_ecuadorian_phone,
)

User = get_user_model()


class CustomUserDetailsSerializer(serializers.ModelSerializer):
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    profile_photo_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()

    def validate_dni(self, value):
        value = validate_ecuadorian_dni(value)
        if value:
            qs = User.objects.filter(dni=value)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError('Esta cédula ya está registrada.')
        return value

    def validate_phone(self, value):
        value = validate_ecuadorian_phone(value)
        if value:
            qs = User.objects.filter(phone=value)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError('Este teléfono ya está registrado.')
        return value

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'dni', 'phone', 'profile_photo', 'profile_photo_url',
            'full_name', 'is_admin', 'role', 'role_label',
            'is_active', 'date_joined',
        ]
        read_only_fields = [
            'id', 'is_active', 'date_joined', 'is_admin',
            'role', 'role_label', 'full_name', 'profile_photo_url',
        ]

    def get_profile_photo_url(self, obj):
        if not obj.profile_photo:
            return ''
        request = self.context.get('request')
        url = obj.profile_photo.url
        return request.build_absolute_uri(url) if request else url

    def get_full_name(self, obj):
        return obj.full_name

    def get_is_admin(self, obj):
        return bool(obj.is_staff or obj.is_superuser)

    def get_role(self, obj):
        return _resolve_role(obj)

    def get_role_label(self, obj):
        return _resolve_role_label(obj)


class CustomRegisterSerializer(RegisterSerializer):
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=True, max_length=150)
    dni = serializers.CharField(required=True, max_length=10, min_length=10)
    phone = serializers.CharField(required=True, max_length=10, min_length=10)
    profile_photo = serializers.ImageField(required=False, allow_null=True)

    def validate_email(self, email):
        email = (email or '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Este correo ya está registrado.')
        return super().validate_email(email)

    def validate_dni(self, value):
        value = validate_ecuadorian_dni(value)
        if value and User.objects.filter(dni=value).exists():
            raise serializers.ValidationError('Esta cédula ya está registrada.')
        return value

    def validate_phone(self, value):
        value = validate_ecuadorian_phone(value)
        if value and User.objects.filter(phone=value).exists():
            raise serializers.ValidationError('Este teléfono ya está registrado.')
        return value

    def validate_password1(self, value):
        _validate_password_strength(value)
        return super().validate_password1(value)

    def validate(self, data):
        data = super().validate(data)
        password1 = data.get('password1') or ''
        password2 = data.get('password2') or ''
        if password1 and password2 and password1 != password2:
            raise serializers.ValidationError({'password2': 'Las contraseñas no coinciden.'})
        return data

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data.update({
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
            'dni': self.validated_data.get('dni', ''),
            'phone': self.validated_data.get('phone', ''),
            'profile_photo': self.validated_data.get('profile_photo', None),
        })
        return data

    def custom_signup(self, request, user):
        data = self.get_cleaned_data()
        user.first_name = data.get('first_name', '')
        user.last_name = data.get('last_name', '')
        user.dni = data.get('dni', '')
        user.phone = data.get('phone', '')
        photo = data.get('profile_photo')
        if photo:
            user.profile_photo = photo
        user.save()

        try:
            send_verification_email(user)
        except Exception:
            pass


GENERIC_LOGIN_ERROR = 'Credenciales inválidas.'


class CustomLoginSerializer(LoginSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(style={'input_type': 'password'})

    def validate(self, attrs):
        username = (attrs.get('username') or '').strip()
        email = (attrs.get('email') or '').strip().lower()
        password = attrs.get('password')
        request = self.context.get('request')
        ip = request.META.get('REMOTE_ADDR') if request else None
        ua = request.META.get('HTTP_USER_AGENT', '') if request else ''

        candidate = None
        if email:
            candidate = User.objects.filter(email__iexact=email).first()
        elif username:
            candidate = User.objects.filter(username__iexact=username).first() \
                or User.objects.filter(email__iexact=username).first()

        attempted_username = candidate.username if candidate else (email or username)

        if candidate and candidate.is_locked():
            record_login_attempt(candidate, attempted_username, ip, ua, successful=False)
            raise serializers.ValidationError({'detail': GENERIC_LOGIN_ERROR})

        user = None
        if candidate:
            user = authenticate(request=request, username=candidate.username, password=password)

        record_login_attempt(
            user=candidate,
            username=attempted_username,
            ip_address=ip,
            user_agent=ua,
            successful=user is not None,
        )

        if not user:
            raise serializers.ValidationError({'detail': GENERIC_LOGIN_ERROR})

        if not user.is_active:
            user.account_locked_until = timezone.now() + timedelta(minutes=15)
            user.save(update_fields=['account_locked_until'])
            raise serializers.ValidationError({'detail': GENERIC_LOGIN_ERROR})

        attrs['user'] = user
        return attrs


def _password_reset_url_generator(request, user, temp_key):
    if 'allauth' in settings.INSTALLED_APPS:
        from allauth.account.utils import user_pk_to_url_str
        uid = user_pk_to_url_str(user)
    else:
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f'{settings.PASSWORD_RESET_FRONTEND_URL}?uid={uid}&token={temp_key}'


class CustomPasswordResetSerializer(PasswordResetSerializer):
    def get_email_options(self):
        return {
            'url_generator': _password_reset_url_generator,
            'extra_email_context': {
                'frontend_url': settings.PASSWORD_RESET_FRONTEND_URL,
            },
        }


class UserSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    profile_photo_url = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'phone', 'dni', 'is_active', 'full_name',
            'profile_photo_url', 'role', 'role_label',
        ]

    def get_full_name(self, obj):
        return obj.full_name

    def get_profile_photo_url(self, obj):
        if not obj.profile_photo:
            return ''
        request = self.context.get('request')
        url = obj.profile_photo.url
        return request.build_absolute_uri(url) if request else url

    def get_role(self, obj):
        return _resolve_role(obj)

    def get_role_label(self, obj):
        return _resolve_role_label(obj)


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            'notifications_enabled', 'language', 'theme',
            'preferences', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class EmailVerificationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailVerificationConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            user_id = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=user_id)
        except Exception as exc:
            raise serializers.ValidationError({'detail': 'Enlace inválido.'}) from exc

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError({'detail': 'Token inválido o expirado.'})

        attrs['user'] = user
        return attrs
