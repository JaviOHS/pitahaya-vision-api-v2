from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.security.utils import validate_ecuadorian_dni, validate_ecuadorian_phone

User = get_user_model()


class DNIValidatorTests(TestCase):
    def test_dni_valida(self):
        self.assertEqual(validate_ecuadorian_dni('1710034065'), '1710034065')

    def test_dni_provincia_invalida(self):
        with self.assertRaises(serializers.ValidationError):
            validate_ecuadorian_dni('9910034065')

    def test_dni_tercer_digito_invalido(self):
        with self.assertRaises(serializers.ValidationError):
            validate_ecuadorian_dni('1760034065')

    def test_dni_no_numerica(self):
        with self.assertRaises(serializers.ValidationError):
            validate_ecuadorian_dni('17abc34065')

    def test_dni_longitud_incorrecta(self):
        with self.assertRaises(serializers.ValidationError):
            validate_ecuadorian_dni('171003406')

    def test_dni_verificador_incorrecto(self):
        with self.assertRaises(serializers.ValidationError):
            validate_ecuadorian_dni('1710034060')


class PhoneValidatorTests(TestCase):
    def test_phone_valido(self):
        self.assertEqual(validate_ecuadorian_phone('0991234567'), '0991234567')

    def test_phone_acepta_separadores_pero_los_limpia(self):
        self.assertEqual(validate_ecuadorian_phone('099 123-4567'), '0991234567')

    def test_phone_sin_cero_inicial(self):
        with self.assertRaises(serializers.ValidationError):
            validate_ecuadorian_phone('1991234567')

    def test_phone_corto(self):
        with self.assertRaises(serializers.ValidationError):
            validate_ecuadorian_phone('0991234')


class RegistrationFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            'username': 'nuevo_user',
            'email': 'nuevo@example.com',
            'password1': 'SuperSecreto1!',
            'password2': 'SuperSecreto1!',
            'first_name': 'Nuevo',
            'last_name': 'Usuario',
            'dni': '1710034065',
            'phone': '0991234567',
        }

    def test_registro_exitoso_crea_usuario_inactivo(self):
        response = self.client.post('/api/v2/auth/registration/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(email=self.payload['email'])
        self.assertFalse(user.is_active, 'Debe quedar inactivo hasta verificar correo')
        self.assertEqual(user.dni, self.payload['dni'])
        self.assertEqual(user.phone, self.payload['phone'])

    def test_registro_con_dni_invalida_falla(self):
        bad = {**self.payload, 'dni': '0000000000'}
        response = self.client.post('/api/v2/auth/registration/', bad, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('dni', response.json())

    def test_registro_con_telefono_invalido_falla(self):
        bad = {**self.payload, 'phone': '12345'}
        response = self.client.post('/api/v2/auth/registration/', bad, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.json())


class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = 'SuperSecreto1!'
        self.user = User.objects.create_user(
            username='login_user', email='login@example.com',
            password=self.password, is_active=True,
        )

    def test_login_con_username(self):
        response = self.client.post('/api/v2/auth/login/', {
            'username': 'login_user', 'password': self.password,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('key', response.json())

    def test_login_con_email(self):
        response = self.client.post('/api/v2/auth/login/', {
            'email': 'login@example.com', 'password': self.password,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('key', response.json())

    def test_login_credenciales_invalidas(self):
        response = self.client.post('/api/v2/auth/login/', {
            'username': 'login_user', 'password': 'mala',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_login_cuenta_inactiva(self):
        self.user.is_active = False
        self.user.save()
        self.client.defaults['REMOTE_ADDR'] = '203.0.113.20'
        response = self.client.post('/api/v2/auth/login/', {
            'username': 'login_user', 'password': self.password,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    @override_settings(
        MAX_LOGIN_ATTEMPTS=6,
        LOGIN_LOCKOUT_MINUTES=5,
        LOGIN_THROTTLE_RATE='20/minute',
        REST_FRAMEWORK={
            'DEFAULT_THROTTLE_RATES': {
                'anon': '30/hour',
                'user': '300/hour',
                'login': '20/minute',
                'register': '5/hour',
                'password_reset': '5/hour',
                'email_verification': '5/minute',
                'availability': '30/minute',
                'authenticated_user': '300/hour',
            }
        },
    )
    def test_login_se_bloquea_después_de_6_intentos_fallidos(self):
        self.client.defaults['REMOTE_ADDR'] = '203.0.113.30'
        for attempt in range(6):
            response = self.client.post('/api/v2/auth/login/', {
                'username': 'login_user', 'password': 'wrong-password',
            }, format='json')
            if response.status_code == 429:
                break
            self.assertEqual(response.status_code, 400)
        locked_user = User.objects.get(pk=self.user.pk)
        self.assertTrue(locked_user.is_locked())
        self.assertIsNotNone(locked_user.account_locked_until)

    @override_settings(
        LOGIN_THROTTLE_RATE='3/minute',
        REST_FRAMEWORK={
            'DEFAULT_THROTTLE_RATES': {
                'anon': '30/hour',
                'user': '300/hour',
                'login': '3/minute',
                'register': '5/hour',
                'password_reset': '5/hour',
                'email_verification': '5/minute',
                'availability': '30/minute',
                'authenticated_user': '300/hour',
            }
        },
    )
    def test_login_throttle_aplica_en_el_4to_intento(self):
        self.client.defaults['REMOTE_ADDR'] = '203.0.113.11'
        for _ in range(3):
            response = self.client.post('/api/v2/auth/login/', {
                'username': 'login_user', 'password': 'wrong-password',
            }, format='json')
            self.assertEqual(response.status_code, 400)

        response = self.client.post('/api/v2/auth/login/', {
            'username': 'login_user', 'password': 'wrong-password',
        }, format='json')
        self.assertEqual(response.status_code, 429)


class ProfileViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='profile_user', password='Pass1234!',
            first_name='Profile', last_name='Test',
        )
        self.client.force_authenticate(user=self.user)

    def test_get_profile(self):
        response = self.client.get('/api/v2/auth/profile/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'profile_user')
        self.assertEqual(response.data['full_name'], 'Profile Test')

    def test_patch_profile(self):
        response = self.client.patch('/api/v2/auth/profile/',
                                      {'first_name': 'Updated'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['first_name'], 'Updated')

    def test_profile_no_autenticado(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v2/auth/profile/')
        self.assertEqual(response.status_code, 401)


class ProfilePreferencesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='pref_user', password='Pass1234!',
        )
        self.client.force_authenticate(user=self.user)

    def test_get_preferences_crea_profile(self):
        response = self.client.get('/api/v2/auth/profile/preferences/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('notifications_enabled', response.data)
        self.assertTrue(response.data['notifications_enabled'])

    def test_patch_preferences(self):
        response = self.client.patch('/api/v2/auth/profile/preferences/', {
            'notifications_enabled': False,
            'notify_severity_threshold': 'critica',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['notifications_enabled'])

    def test_preferences_no_autenticado(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v2/auth/profile/preferences/')
        self.assertEqual(response.status_code, 401)


class DeleteAccountTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='delete_user', password='Pass1234!',
        )
        self.client.force_authenticate(user=self.user)

    def test_delete_account(self):
        response = self.client.post('/api/v2/auth/account/delete/', {'password': 'Pass1234!'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_delete_account_sin_password(self):
        response = self.client.post('/api/v2/auth/account/delete/', format='json')
        self.assertEqual(response.status_code, 403)

    def test_delete_account_password_incorrecto(self):
        response = self.client.post('/api/v2/auth/account/delete/', {'password': 'wrong'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_delete_account_no_autenticado(self):
        self.client.force_authenticate(user=None)
        response = self.client.post('/api/v2/auth/account/delete/', format='json')
        self.assertEqual(response.status_code, 401)


class EmailVerificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='verify_user', email='verify@test.com',
            password='Pass1234!', is_active=False,
        )

    def test_request_verification_email(self):
        response = self.client.post('/api/v2/auth/email/verify/request/', {
            'email': 'verify@test.com',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Si el correo existe', response.data['detail'])

    def test_request_verification_email_no_existe(self):
        response = self.client.post('/api/v2/auth/email/verify/request/', {
            'email': 'no_existe@test.com',
        }, format='json')
        self.assertEqual(response.status_code, 200)

    def test_confirm_verification_exitoso(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        from apps.security.utils import email_verification_token_generator

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = email_verification_token_generator.make_token(self.user)
        response = self.client.post('/api/v2/auth/email/verify/confirm/', {
            'uid': uid, 'token': token,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertTrue(self.user.is_active)

    def test_confirm_verification_token_invalido(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.post('/api/v2/auth/email/verify/confirm/', {
            'uid': uid, 'token': 'token-invalido',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_confirm_verification_uid_invalido(self):
        response = self.client.post('/api/v2/auth/email/verify/confirm/', {
            'uid': 'uid-invalido', 'token': 'token',
        }, format='json')
        self.assertEqual(response.status_code, 400)


class CheckAvailabilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='avail_user', email='avail@test.com',
            password='Pass1234!',
        )
        self.client.force_authenticate(user=self.user)

    def test_availability_username_disponible(self):
        response = self.client.get('/api/v2/auth/availability/',
                                    {'field': 'username', 'value': 'no_existe'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['available'])

    def test_availability_username_ocupado(self):
        response = self.client.get('/api/v2/auth/availability/',
                                    {'field': 'username', 'value': 'avail_user'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['available'])

    def test_availability_email_disponible(self):
        response = self.client.get('/api/v2/auth/availability/',
                                    {'field': 'email', 'value': 'nuevo@test.com'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['available'])

    def test_availability_email_ocupado(self):
        response = self.client.get('/api/v2/auth/availability/',
                                    {'field': 'email', 'value': 'avail@test.com'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['available'])

    def test_availability_parametros_invalidos(self):
        response = self.client.get('/api/v2/auth/availability/',
                                    {'field': 'invalido', 'value': 'test'})
        self.assertEqual(response.status_code, 400)

    def test_availability_no_autenticado(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v2/auth/availability/',
                                    {'field': 'username', 'value': 'test'})
        self.assertEqual(response.status_code, 401)

    def test_availability_dni(self):
        response = self.client.get('/api/v2/auth/availability/',
                                    {'field': 'dni', 'value': '1710034065'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['available'])

    def test_availability_phone(self):
        response = self.client.get('/api/v2/auth/availability/',
                                    {'field': 'phone', 'value': '0999999999'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['available'])


class CustomerManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username='admin_cust', email='admin_cust@test.com',
            password='Admin1234!',
        )
        self.user = User.objects.create_user(
            username='customer_test', password='Pass1234!',
        )
        self.client.force_authenticate(user=self.admin)

    def test_list_customers(self):
        response = self.client.get('/api/v2/auth/customers/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertGreater(len(response.data['results']), 1)

    def test_no_admin_no_acceso(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/v2/auth/customers/')
        self.assertEqual(response.status_code, 403)

    def test_toggle_active(self):
        response = self.client.post(
            f'/api/v2/auth/customers/{self.user.pk}/toggle_active/', format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_toggle_active_no_auto(self):
        response = self.client.post(
            f'/api/v2/auth/customers/{self.admin.pk}/toggle_active/', format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_set_role_admin(self):
        response = self.client.post(
            f'/api/v2/auth/customers/{self.user.pk}/set_role/',
            {'role': 'admin'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)

    def test_set_role_usuario(self):
        self.user.is_staff = True
        self.user.save()
        response = self.client.post(
            f'/api/v2/auth/customers/{self.user.pk}/set_role/',
            {'role': 'usuario'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_set_role_invalido(self):
        response = self.client.post(
            f'/api/v2/auth/customers/{self.user.pk}/set_role/',
            {'role': 'otro'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_set_role_no_auto(self):
        response = self.client.post(
            f'/api/v2/auth/customers/{self.admin.pk}/set_role/',
            {'role': 'usuario'}, format='json',
        )
        self.assertEqual(response.status_code, 400)


class ExpiringTokenAuthTests(TestCase):
    def test_token_expirado(self):
        from datetime import timedelta
        from django.utils import timezone
        from rest_framework.authtoken.models import Token
        user = User.objects.create_user(
            username='token_test', password='Pass1234!',
        )
        token = Token.objects.create(user=user)
        token.created = timezone.now() - timedelta(hours=1)
        token.save()
        with patch('apps.security.authentication.TOKEN_EXPIRY_HOURS', 0):
            from apps.security.authentication import ExpiringTokenAuthentication
            from rest_framework.exceptions import AuthenticationFailed
            with self.assertRaises(AuthenticationFailed):
                auth = ExpiringTokenAuthentication()
                auth.authenticate_credentials(token.key)


class PermissionTests(TestCase):
    def test_is_admin(self):
        from apps.security.permissions import is_admin
        user = User(is_staff=False, is_superuser=False)
        self.assertFalse(is_admin(user))
        user.is_staff = True
        self.assertTrue(is_admin(user))
        user.is_staff = False
        user.is_superuser = True
        self.assertTrue(is_admin(user))

    def test_is_admin_none(self):
        from apps.security.permissions import is_admin
        self.assertFalse(is_admin(None))

    def test_get_admin_users(self):
        from apps.security.permissions import get_admin_users
        User.objects.create_superuser(username='su1', email='su1@t.com', password='Pass1234!')
        User.objects.create_user(username='u1', password='Pass1234!', is_staff=True)
        User.objects.create_user(username='u2', password='Pass1234!')
        admins = get_admin_users()
        self.assertGreaterEqual(admins.count(), 2)

    def test_is_admin_permission(self):
        from apps.security.permissions import IsAdmin
        perm = IsAdmin()
        request = MagicMock()
        request.user = User(is_staff=True)
        self.assertTrue(perm.has_permission(request, None))
        request.user = User(is_staff=False)
        self.assertFalse(perm.has_permission(request, None))

    def test_is_admin_or_read_only(self):
        from apps.security.permissions import IsAdminOrReadOnly
        perm = IsAdminOrReadOnly()
        request = MagicMock()
        request.method = 'GET'
        request.user = MagicMock(is_authenticated=True)
        self.assertTrue(perm.has_permission(request, None))
        request.method = 'POST'
        request.user = MagicMock(is_authenticated=True, is_staff=False, is_superuser=False)
        self.assertFalse(perm.has_permission(request, None))
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=False)
        self.assertTrue(perm.has_permission(request, None))


class ThrottleTests(TestCase):
    def test_login_throttle_rate_desde_settings(self):
        with override_settings(LOGIN_THROTTLE_RATE='5/minute'):
            from apps.security.throttles import LoginRateThrottle
            throttle = LoginRateThrottle()
            self.assertEqual(throttle.get_rate(), '5/minute')


class UserModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='model_user', password='Pass1234!',
            first_name='Model', last_name='User',
        )

    def test_full_name_property(self):
        self.assertEqual(self.user.full_name, 'Model User')
        self.user.first_name = ''
        self.user.last_name = ''
        self.user.save()
        self.assertEqual(self.user.full_name, 'model_user')

    def test_is_locked_false_por_defecto(self):
        self.assertFalse(self.user.is_locked())

    def test_is_locked_true_cuando_bloqueado(self):
        from django.utils import timezone
        self.user.account_locked_until = timezone.now() + timezone.timedelta(hours=1)
        self.user.save()
        self.assertTrue(self.user.is_locked())

    def test_is_locked_se_limpia_si_expiro(self):
        from django.utils import timezone
        self.user.account_locked_until = timezone.now() - timezone.timedelta(hours=1)
        self.user.save()
        self.assertFalse(self.user.is_locked())
        self.user.refresh_from_db()
        self.assertIsNone(self.user.account_locked_until)

    def test_set_password_guarda_history(self):
        self.user.set_password('NuevaPass1!')
        from apps.security.models import PasswordHistory
        self.assertTrue(PasswordHistory.objects.filter(user=self.user).exists())


class PasswordHistoryValidatorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='phv_user', password='Pass1234!',
        )
        self.validator = __import__('apps.security.utils',
                                     fromlist=['PasswordHistoryValidator']).PasswordHistoryValidator

    def test_validate_historico(self):
        from django.contrib.auth.hashers import make_password
        from apps.security.models import PasswordHistory
        PasswordHistory.objects.create(
            user=self.user,
            password_hash=make_password('PassAnterior1!'),
        )
        validator = self.validator()
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validator.validate('PassAnterior1!', user=self.user)

    def test_validate_no_user(self):
        validator = self.validator()
        try:
            validator.validate('CualquierCosa1!', user=None)
        except Exception:
            self.fail('No debería lanzar excepción con user=None')

    def test_get_help_text(self):
        validator = self.validator()
        self.assertIn('no debe haber sido utilizada', validator.get_help_text())


class UtilsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='utils_user', password='Pass1234!',
        )

    def test_resolve_role_admin(self):
        from apps.security.utils import _resolve_role, _resolve_role_label
        user = User(is_staff=True)
        self.assertEqual(_resolve_role(user), 'admin')
        self.assertEqual(_resolve_role_label(user), 'Administrador')

    def test_resolve_role_usuario(self):
        from apps.security.utils import _resolve_role, _resolve_role_label
        user = User(is_staff=False, is_superuser=False)
        self.assertEqual(_resolve_role(user), 'usuario')
        self.assertEqual(_resolve_role_label(user), 'Usuario')

    def test_notifications_enabled_for_sin_profile(self):
        from apps.security.utils import notifications_enabled_for
        user = User()
        self.assertTrue(notifications_enabled_for(user))

    def test_email_verification_token_generator(self):
        from apps.security.utils import email_verification_token_generator
        token = email_verification_token_generator.make_token(self.user)
        self.assertTrue(email_verification_token_generator.check_token(self.user, token))
        self.assertFalse(email_verification_token_generator.check_token(self.user, 'fake'))

    def test_record_login_attempt(self):
        from apps.security.utils import record_login_attempt
        user = User.objects.create_user(username='attempt_user', password='Pass1234!')
        record_login_attempt(user=user, username='attempt_user', successful=True)
        from apps.security.models import LoginAttempt
        self.assertEqual(LoginAttempt.objects.filter(user=user).count(), 1)

    def test_record_login_attempt_bloqueo(self):
        from apps.security.utils import record_login_attempt
        user = User.objects.create_user(username='lock_test', password='Pass1234!')
        for _ in range(6):
            record_login_attempt(user=user, username='lock_test', successful=False)
        user.refresh_from_db()
        self.assertTrue(user.is_locked())


class ExceptionHandlerTests(TestCase):
    def test_throttled_exception_handler(self):
        from rest_framework.exceptions import Throttled
        from apps.security.exceptions import custom_exception_handler
        context = {'view': None, 'request': None, 'args': (), 'kwargs': {}}
        exc = Throttled(wait=30)
        response = custom_exception_handler(exc, context)
        self.assertIsNotNone(response)
        self.assertIn('wait', response.data)
        self.assertEqual(response.data['wait'], 30)
        self.assertIn('demasiados intentos', response.data['detail'])

