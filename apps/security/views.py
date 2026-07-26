import logging

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from dj_rest_auth.registration.views import RegisterView
from dj_rest_auth.views import LoginView as RestLoginView
from dj_rest_auth.views import PasswordResetView as RestPasswordResetView

from .serializers import (
    CustomUserDetailsSerializer,
    ProfileSerializer,
    UserSummarySerializer,
    EmailVerificationConfirmSerializer,
    EmailVerificationRequestSerializer,
    send_verification_email,
)
from .throttles import (
    LoginRateThrottle,
    RegisterRateThrottle,
    PasswordResetRateThrottle,
    EmailVerificationRateThrottle,
    AvailabilityRateThrottle,
)
from .utils import send_notification_email, notify_admins
from .models import Profile
from .permissions import IsAdmin

logger = logging.getLogger(__name__)
User = get_user_model()


class ProfileView(APIView):
    """Vista para que los usuarios vean y actualicen su propio perfil."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        serializer = CustomUserDetailsSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    def patch(self, request):
        serializer = CustomUserDetailsSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ProfilePreferencesView(APIView):
    """Vista para que los usuarios vean y actualicen sus preferencias de perfil."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)

    def patch(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(
            profile,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def delete_account_view(request):
    """Vista para que los usuarios desactiven su propia cuenta (requiere contraseña)."""
    password = request.data.get('password', '')
    if not request.user.check_password(password):
        return Response({'detail': 'Contraseña incorrecta.'}, status=status.HTTP_403_FORBIDDEN)
    user = request.user
    user.is_active = False
    user.deactivated_at = timezone.now()
    user.save(update_fields=['is_active', 'deactivated_at'])
    return Response(
        {'detail': 'Cuenta desactivada. Puedes contactar al administrador si deseas reactivarla.'},
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([EmailVerificationRateThrottle])
def request_verification_email(request):
    """Vista para solicitar un correo de verificación."""
    serializer = EmailVerificationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = User.objects.filter(email__iexact=serializer.validated_data['email']).first()
    if user:
        send_verification_email(user)
    return Response({'detail': 'Si el correo existe, te enviamos un enlace de verificación.'})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def confirm_verification_email(request):
    """Vista para confirmar la verificación de correo."""
    serializer = EmailVerificationConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data['user']
    update_fields = []
    if not user.is_active:
        user.is_active = True
        update_fields.append('is_active')
    if not user.email_verified:
        user.email_verified = True
        update_fields.append('email_verified')
    if update_fields:
        user.save(update_fields=update_fields)
    return Response({'detail': 'Cuenta verificada correctamente.'})


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@throttle_classes([AvailabilityRateThrottle])
def check_availability(request):
    """Vista para verificar en tiempo real si un dato (username/email/dni/phone) ya está registrado."""
    field = (request.query_params.get('field') or '').strip().lower()
    value = (request.query_params.get('value') or '').strip()

    lookups = {
        'username': lambda v: User.objects.filter(username__iexact=v),
        'email': lambda v: User.objects.filter(email__iexact=v),
        'dni': lambda v: User.objects.filter(dni=v),
        'phone': lambda v: User.objects.filter(phone=v),
    }

    if field not in lookups or not value:
        return Response(
            {'detail': 'Parámetros inválidos. Usa field=username|email|dni|phone y un value no vacío.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    exists = lookups[field](value).exists()
    return Response({'available': not exists})


class CustomerViewSet(ModelViewSet):
    """Vista para que los administradores gestionen las cuentas de los usuarios."""
    http_method_names = ['get', 'post']
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    queryset = User.objects.order_by('-date_joined')
    serializer_class = UserSummarySerializer

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Método no permitido.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        target = self.get_object()
        if target.id == request.user.id:
            return Response({'detail': 'No puedes deshabilitar tu propia cuenta.'},
                            status=status.HTTP_400_BAD_REQUEST)
        target.is_active = not target.is_active
        target.deactivated_at = None if target.is_active else timezone.now()
        target.save(update_fields=['is_active', 'deactivated_at'])
        if target.is_active:
            send_notification_email(
                target,
                subject='Tu cuenta fue reactivada · Pitahaya Vision',
                heading='Cuenta reactivada',
                message='Un administrador reactivó tu cuenta. Ya puedes iniciar sesión con normalidad.',
            )
        else:
            send_notification_email(
                target,
                subject='Tu cuenta fue suspendida · Pitahaya Vision',
                heading='Cuenta suspendida',
                message='Un administrador suspendió temporalmente tu cuenta. Ponte en contacto con el administrador para habilitar tu acceso nuevamente.',
            )
        serializer = self.get_serializer(target)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def set_role(self, request, pk=None):
        target = self.get_object()
        if target.id == request.user.id:
            return Response({'detail': 'No puedes cambiar tu propio rol.'},
                            status=status.HTTP_400_BAD_REQUEST)
        new_role = (request.data.get('role') or '').strip().lower()
        if new_role not in ('admin', 'usuario'):
            return Response({'detail': 'Rol inválido. Usa "admin" o "usuario".'},
                            status=status.HTTP_400_BAD_REQUEST)
        target.is_staff = (new_role == 'admin')
        if new_role == 'usuario':
            target.is_superuser = False
        target.save(update_fields=['is_staff', 'is_superuser'])
        serializer = self.get_serializer(target)
        return Response(serializer.data)


class CustomLoginView(RestLoginView):
    throttle_classes = [LoginRateThrottle]


class CustomPasswordResetView(RestPasswordResetView):
    throttle_classes = [PasswordResetRateThrottle]


class CustomRegisterView(RegisterView):
    """Vista personalizada para el registro de usuarios que desactiva la cuenta hasta que se verifique el correo."""
    throttle_classes = [RegisterRateThrottle]

    def perform_create(self, serializer):
        user = serializer.save(self.request)
        user.is_active = False
        user.save(update_fields=['is_active'])
        notify_admins(
            subject='Nuevo usuario registrado · Pitahaya Vision',
            heading='Nuevo usuario registrado',
            message=f'"{user.get_full_name() or user.username}" ({user.email}) se registró y está pendiente de verificar su correo.',
            details=[
                {'label': 'Usuario', 'value': user.username},
                {'label': 'Correo', 'value': user.email},
                {'label': 'Fecha de registro', 'value': user.date_joined.strftime('%d/%m/%Y %H:%M')},
            ],
        )
        return user

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {'detail': 'Cuenta creada. Te enviamos un enlace para verificar tu correo y activar tu cuenta.'},
            status=status.HTTP_201_CREATED,
        )
