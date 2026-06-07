from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env', override=True)

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-me')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('1', 'true', 'yes')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'apps.security',
    # 'apps.analysis',
    # 'apps.chatbot',
    # 'apps.knowledge',
]

MIGRATION_MODULES = {
    'security': 'apps.security.migrations',
    # 'analysis': 'apps.analysis.migrations',
    # 'chatbot': 'apps.chatbot.migrations',
    # 'knowledge': 'apps.knowledge.migrations',
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.sites.middleware.CurrentSiteMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

AUTH_USER_MODEL = 'security.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Database (PostgreSQL o SQLite según DB_ENGINE) ---
DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite')
if DB_ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'pitahaya_vision_db'),
            'USER': os.getenv('DB_USER', 'pitahaya_user'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'pitahaya_pass'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-ec'
TIME_ZONE = os.getenv('TIME_ZONE', 'America/Guayaquil')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- DRF ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# # --- CORS ---
cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173')
CORS_ALLOWED_ORIGINS = [o.strip() for o in cors_origins.split(',')]
CORS_ALLOW_CREDENTIALS = True

# # --- django-allauth / dj-rest-auth ---
SITE_ID = 1
ACCOUNT_EMAIL_VERIFICATION = os.getenv('ACCOUNT_EMAIL_VERIFICATION', 'none')
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGOUT_ON_GET = True
LOGIN_URL = '/api/v1/auth/login/'

REST_AUTH = {
    'REGISTER_SERIALIZER': 'apps.security.serializers.CustomRegisterSerializer',
    'LOGIN_SERIALIZER': 'apps.security.serializers.CustomLoginSerializer',
    'PASSWORD_RESET_SERIALIZER': 'apps.security.serializers.CustomPasswordResetSerializer',
    'USER_DETAILS_SERIALIZER': 'apps.security.serializers.CustomUserDetailsSerializer',
    'TOKEN_MODEL': 'rest_framework.authtoken.models.Token',
}

# --- Email ---
# Backend usado para enviar correos. Dos opciones:
#   - console (default en desarrollo): imprime los correos en la terminal
#     donde corre `runserver`. Útil para pruebas sin SMTP.
#   - smtp: envía correos reales vía SMTP (Gmail, etc.).
# Se configura en .env con EMAIL_BACKEND. Si no está definido, se
# elige automáticamente: console en desarrollo, smtp en producción.
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
)

# Dirección que aparece como remitente en los correos
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@pitahaya-vision.local')

# URLs del frontend usadas en los enlaces de los correos
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
EMAIL_VERIFICATION_FRONTEND_URL = os.getenv(
    'EMAIL_VERIFICATION_FRONTEND_URL',
    'http://localhost:5173/verificar-correo'
)
PASSWORD_RESET_FRONTEND_URL = os.getenv(
    'PASSWORD_RESET_FRONTEND_URL',
    'http://localhost:5173/recuperar-cuenta/confirmar'
)

# Configuración SMTP — solo aplica cuando el backend es smtp
if 'smtp' in EMAIL_BACKEND:
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('1', 'true', 'yes')
    EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('1', 'true', 'yes')

# --- External microservices ---
# CHATBOT_SERVICE_URL = os.getenv('CHATBOT_SERVICE_URL', '')
# CHATBOT_SERVICE_TIMEOUT = int(os.getenv('CHATBOT_SERVICE_TIMEOUT', '120'))
# ANALYSIS_SERVICE_URL = os.getenv('ANALYSIS_SERVICE_URL', '')
# ANALYSIS_SERVICE_TIMEOUT = int(os.getenv('ANALYSIS_SERVICE_TIMEOUT', '60'))
