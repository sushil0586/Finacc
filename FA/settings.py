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


def _cast_boolish_env(value):
    if isinstance(value, bool):
        return value
    raw = str(value or '').strip().lower()
    if raw in {'1', 'true', 't', 'yes', 'y', 'on', 'debug', 'dev', 'development'}:
        return True
    if raw in {'0', 'false', 'f', 'no', 'n', 'off', 'release', 'prod', 'production', ''}:
        return False
    raise ValueError(f'Invalid truth value: {value}')


def _normalize_storage_backend(value):
    backend = str(value or 'local').strip().lower()
    if backend not in {'local', 's3'}:
        raise ValueError(f'Invalid FILE_STORAGE_BACKEND: {value}')
    return backend


def _require_config(name):
    value = str(config(name, default='')).strip()
    if not value:
        raise ValueError(f'Missing required setting: {name}')
    return value

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=_cast_boolish_env)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost', cast=Csv())

# RBAC bypass must be enabled explicitly.
# Keep it separate from DEBUG so local development can still exercise
# real tenant/membership/RBAC behavior by default.
RBAC_DEV_ALLOW_ALL_ACCESS = config(
    'RBAC_DEV_ALLOW_ALL_ACCESS',
    default=False,
    cast=_cast_boolish_env,
)

FILE_STORAGE_BACKEND = config(
    'FILE_STORAGE_BACKEND',
    default='local',
    cast=_normalize_storage_backend,
)

CACHE_BACKEND = config('CACHE_BACKEND', default='locmem')
CACHE_LOCATION = config('CACHE_LOCATION', default='finacc-cache')
CACHE_TIMEOUT_SECONDS = config('CACHE_TIMEOUT_SECONDS', default=300, cast=int)
META_CACHE_ENABLED = config('META_CACHE_ENABLED', default=True, cast=_cast_boolish_env)
META_CACHE_TTL_SECONDS = config('META_CACHE_TTL_SECONDS', default=300, cast=int)
META_CACHE_FORM_TTL_SECONDS = config('META_CACHE_FORM_TTL_SECONDS', default=600, cast=int)
META_CACHE_SETTINGS_TTL_SECONDS = config('META_CACHE_SETTINGS_TTL_SECONDS', default=300, cast=int)
META_CACHE_VERSION = config('META_CACHE_VERSION', default='1')
META_CACHE_OBSERVABILITY_ENABLED = config('META_CACHE_OBSERVABILITY_ENABLED', default=False, cast=_cast_boolish_env)
META_CACHE_LOG_LEVEL = config('META_CACHE_LOG_LEVEL', default='INFO')

# ---------------------------------------------------------------------------
# Test / conditional app flags
# ---------------------------------------------------------------------------
RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == 'test'
ENABLE_PAYROLL_IN_TESTS = config('ENABLE_PAYROLL_IN_TESTS', default=False, cast=_cast_boolish_env)

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
    'dashboard',
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
    "inventory_ops",
    "commerce",
    "manufacturing",
    "retail",
    "assets",
    "sales.apps.SalesConfig",
    "withholding",
    "gst_tds",
    "rbac",
    "subscriptions",
    "bank_reconciliation.apps.BankReconciliationConfig",
]

INSTALLED_APPS += ['auditlogger']

if FILE_STORAGE_BACKEND == 's3':
    INSTALLED_APPS += ['storages']

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
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

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
        'NAME': config('DB_NAME', default='FA'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default=''),
    }
}

DATABASES['default']['TEST'] = {
    'NAME': config('DB_TEST_NAME', default=f"test_{DATABASES['default']['NAME']}"),
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

if CACHE_BACKEND == 'redis':
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _require_config('CACHE_LOCATION'),
            'TIMEOUT': CACHE_TIMEOUT_SECONDS,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': CACHE_LOCATION,
            'TIMEOUT': CACHE_TIMEOUT_SECONDS,
        }
    }

if FILE_STORAGE_BACKEND == 's3':
    AWS_STORAGE_BUCKET_NAME = _require_config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='ap-south-1')
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
    AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='')
    AWS_MEDIA_LOCATION = config('AWS_MEDIA_LOCATION', default='')
    AWS_QUERYSTRING_AUTH = config('AWS_QUERYSTRING_AUTH', default=True, cast=_cast_boolish_env)
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_SIGNATURE_VERSION = 's3v4'

    if bool(AWS_ACCESS_KEY_ID) != bool(AWS_SECRET_ACCESS_KEY):
        raise ValueError('Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY together, or leave both empty to use IAM role.')

    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                'bucket_name': AWS_STORAGE_BUCKET_NAME,
                'region_name': AWS_S3_REGION_NAME,
                'default_acl': AWS_DEFAULT_ACL,
                'querystring_auth': AWS_QUERYSTRING_AUTH,
                'file_overwrite': AWS_S3_FILE_OVERWRITE,
                'location': AWS_MEDIA_LOCATION,
            },
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        STORAGES['default']['OPTIONS']['access_key'] = AWS_ACCESS_KEY_ID
        STORAGES['default']['OPTIONS']['secret_key'] = AWS_SECRET_ACCESS_KEY

    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    elif AWS_S3_REGION_NAME:
        MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/'
    else:
        MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'

    if AWS_MEDIA_LOCATION:
        MEDIA_URL = MEDIA_URL.rstrip('/') + f'/{AWS_MEDIA_LOCATION.strip("/")}/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Reverse proxy / HTTPS deployment
# ---------------------------------------------------------------------------
USE_X_FORWARDED_HOST = config('USE_X_FORWARDED_HOST', default=True, cast=_cast_boolish_env)
USE_X_FORWARDED_PORT = config('USE_X_FORWARDED_PORT', default=True, cast=_cast_boolish_env)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=_cast_boolish_env)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=_cast_boolish_env)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=not DEBUG, cast=_cast_boolish_env)

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
AUTH_REQUIRE_EMAIL_VERIFIED = False

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
