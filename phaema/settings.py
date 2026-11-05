# SPDX-License-Identifier: AGPL-3.0-or-later
"""PHAEMA settings. All deployment-specific values come from environment variables."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="insecure-development-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# Behind a reverse proxy that ends HTTPS (nginx, Caddy, a load balancer), Django only sees plain HTTP.
# Set BEHIND_HTTPS_PROXY=True so it trusts the proxy's X-Forwarded-Proto header and treats requests
# as secure. Only do this when PHAEMA can be reached through the proxy alone (docker-compose binds the
# app to 127.0.0.1 for this reason), otherwise a client could claim HTTPS itself.
if env.bool("BEHIND_HTTPS_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# The public address is always a trusted origin for forms, so a correct PHAEMA_BASE_URL is enough.
_base_url = env("PHAEMA_BASE_URL", default="http://localhost:8000").rstrip("/")
if _base_url.startswith("https://") and _base_url not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, _base_url]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.gis",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.properties",
    "apps.leases",
    "apps.reports",
    "apps.imports",
    "apps.help",
    "apps.ledger",
    "apps.servicecharges",
    "apps.cases",
    "apps.maintenance",
    "apps.compliance",
    "apps.valuations",
    "apps.documents",
    "apps.projects",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.CurrentUserMiddleware",
    "apps.core.middleware.RoleRequiredMiddleware",
]

ROOT_URLCONF = "phaema.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.phaema",
            ],
        },
    },
]

WSGI_APPLICATION = "phaema.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgis://phaema:phaema@localhost:5432/phaema"
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalisation: English now, Welsh (cy) structure in place for Welsh councils.
LANGUAGE_CODE = "en-gb"
LANGUAGES = [("en", "English"), ("cy", "Cymraeg")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/files/"  # served by a view that requires sign-in
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

LOGIN_URL = "login"
FILE_UPLOAD_PERMISSIONS = 0o640
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["apps.core.api_permissions.PhaemaPermission"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "PHAEMA API",
    "DESCRIPTION": "Property Holding and Estate Management Application: open API.",
    "VERSION": "0.1.0",
    "LICENSE": {"name": "AGPL-3.0-or-later"},
}

# Security settings for production (DEBUG off).
if not DEBUG:
    SESSION_COOKIE_SECURE = env.bool("SECURE_COOKIES", default=True)
    CSRF_COOKIE_SECURE = env.bool("SECURE_COOKIES", default=True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

# Email (reminders). Without EMAIL_HOST, emails are written to the log instead of being sent.
if env("EMAIL_HOST", default=""):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="PHAEMA <phaema@localhost>")
# The web address of this PHAEMA, used for links in emails, e.g. https://phaema.example.gov.uk
PHAEMA_BASE_URL = env("PHAEMA_BASE_URL", default="http://localhost:8000")

# Name of the organisation shown in the header, e.g. "Example District Council".
PHAEMA_ORGANISATION_NAME = env("PHAEMA_ORGANISATION_NAME", default="Demonstration Council")
