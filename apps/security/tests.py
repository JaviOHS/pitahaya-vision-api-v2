from django.contrib.auth import get_user_model
from django.test import TestCase
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
        response = self.client.post('/api/v2/auth/login/', {
            'username': 'login_user', 'password': self.password,
        }, format='json')
        self.assertEqual(response.status_code, 400)
