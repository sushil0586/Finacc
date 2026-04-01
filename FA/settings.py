"""
Django settings for FA project.
"""
from pathlib import Path
from decouple import config, Csv
import os
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost', cast=Csv())

# RBAC: only bypass access checks in real development (DEBUG=True in .env).
# Never True in production because DEBUG will be False there.
RBAC_DEV_ALLOW_ALL_ACCESS = DEBUG

# ---------------------------------------------------------------------------
# Test / conditional app flags
# ---------------------------------------------------------------------------
RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == 'test'
ENABLE_PAYROLL_IN_TESTS = config('ENABLE_PAYROLL_IN_TESTS', default=False, cast=bool)

AUTH_USER_MODEL = "Authentication.User"

# ---------------------------------------------------------------------------
# Installed apps
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'Authentication',
    'django_filters',
    'drf_yasg',
    'entity',
    'geography',
    'financial',
    'corsheaders',
    'drf_excel',
    'import_export',
    'payroll',
    'reports',
    'simple_history',
    'errorlogger',
    'numbering',
    'catalog',
    "localization",
    "purchase",
    "payments",
    "receipts",
    "vouchers",
    "posting",
    "assets",
    "sales.apps.SalesConfig",
    "withholding",
    "gst_tds",
    "rbac",
    "subscriptions",
]

INSTALLED_APPS += ['auditlogger']

if RUNNING_TESTS and not ENABLE_PAYROLL_IN_TESTS:
    INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'payroll']

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    'errorlogger.middleware.GlobalExceptionLoggingMiddleware',
]

MIDDLEWARE.insert(0, 'auditlogger.middleware.AuditMiddleware')

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ORIGIN_ALLOW_ALL = config('CORS_ORIGIN_ALLOW_ALL', default=False, cast=bool)
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# URLs / Templates / WSGI
# ---------------------------------------------------------------------------
ROOT_URLCONF = 'FA.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'FA.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
   'default': {
       'ENGINE': 'django.db.backends.postgresql',
       'NAME': 'finacc',
       'USER': 'finaccuser',
       'PASSWORD': 'Ansh@1789',
       'HOST': 'localhost',
       'PORT': '5432',

   }
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'COERCE_DECIMAL_TO_STRING': False,
    'DATETIME_FORMAT': '%d-%m-%Y',
    'DATE_FORMAT': '%d-%m-%Y',
    'URL_FORMAT_OVERRIDE': None,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'Authentication.jwt.JwtAuthentication',
    ],
    'EXCEPTION_HANDLER': 'errorlogger.drf_exception_handler.custom_exception_handler',
    'DATE_INPUT_FORMATS': [
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
    ],
}

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# GST / e-Invoice / e-Way Bill
# ---------------------------------------------------------------------------
EINVOICE_PROVIDER = config('EINVOICE_PROVIDER', default='whitebooks')
EWAY_PROVIDER = config('EWAY_PROVIDER', default='whitebooks')
MASTERGST_ENV = config('MASTERGST_ENV', default='SANDBOX')
MASTERGST_BASE_URL = config('MASTERGST_BASE_URL', default='https://api.mastergst.com')
MASTERGST_IP_ADDRESS = config('MASTERGST_IP_ADDRESS', default='')
WHITEBOOKS_BASE_URL = config('WHITEBOOKS_BASE_URL', default='https://apisandbox.whitebooks.in')
GST_PROVIDER_BASE_URLS = {
    'mastergst': MASTERGST_BASE_URL,
    'whitebooks': WHITEBOOKS_BASE_URL or MASTERGST_BASE_URL,
}
ALLOW_RELAXED_GSTIN_FOR_SANDBOX = config('ALLOW_RELAXED_GSTIN_FOR_SANDBOX', default=False, cast=bool)
FINANCIAL_ACCOUNT_ALLOW_RELAXED_GSTIN = config('FINANCIAL_ACCOUNT_ALLOW_RELAXED_GSTIN', default=False, cast=bool)

# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
OPENAI_API_KEY = config('OPENAI_API_KEY', default='')
OPENAI_MODEL = config('OPENAI_MODEL', default='gpt-4o')

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=20, cast=int)
AUTH_REQUIRE_EMAIL_VERIFIED = True

# ---------------------------------------------------------------------------
# Auth cookies (httpOnly token storage)
# ---------------------------------------------------------------------------
AUTH_COOKIE_NAME = 'fa_access'
AUTH_REFRESH_COOKIE_NAME = 'fa_refresh'
AUTH_COOKIE_SECURE = not DEBUG      # True in production (HTTPS only), False in dev
AUTH_COOKIE_HTTPONLY = True
AUTH_COOKIE_SAMESITE = 'Lax'        # 'None' if frontend/backend on different domains
AUTH_COOKIE_PATH = '/'

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'error.log'),
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
