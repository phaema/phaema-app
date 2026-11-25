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

DEBUG = env("DEBUG")
# The secret key signs sessions, password reset links and two-step sign-in. A known key would let anyone forge
# them, so PHAEMA refuses to start without a proper one unless DEBUG is on (development on a laptop).
_DEV_KEYS = {"", "insecure-development-key-change-me", "local-development-only-change-me",
             "change-me-to-a-long-random-string"}
SECRET_KEY = env("SECRET_KEY", default="")
if SECRET_KEY in _DEV_KEYS or len(SECRET_KEY) < 32:
    import sys

    if DEBUG or env.bool("PHAEMA_ALLOW_DEV_SECRET_KEY", default=False) or "pytest" in sys.modules:
        SECRET_KEY = SECRET_KEY if len(SECRET_KEY) >= 32 else "insecure-development-key-change-me-0123456789"
    else:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "SECRET_KEY is missing, too short (under 32 characters) or a published example. Set a long random "
            "SECRET_KEY in .env (deploy/install-server.sh does this), or set DEBUG=True on a development computer.")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# Behind a reverse proxy that ends HTTPS (nginx, Caddy, a load balancer), Django only sees plain HTTP.
# Set BEHIND_HTTPS_PROXY=True so it trusts the proxy's X-Forwarded-Proto header and treats requests
# as secure. Only do this when PHAEMA can be reached through the proxy alone (docker-compose binds the
# app to 127.0.0.1 for this reason), otherwise a client could claim HTTPS itself.
PHAEMA_BEHIND_HTTPS_PROXY = env.bool("BEHIND_HTTPS_PROXY", default=False)
if PHAEMA_BEHIND_HTTPS_PROXY:
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
    "apps.connectors",
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
    "apps.strategy",
    "apps.space",
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
    "apps.core.middleware.IdleTimeoutMiddleware",
    "apps.core.middleware.AccessEndedMiddleware",
    "apps.core.middleware.RoleRequiredMiddleware",
    "apps.core.middleware.TwoStepRequiredMiddleware",
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

# One cache shared by every web worker and the scheduler, kept in a database table (made by createcachetable,
# which runs with the migrations). Sign-in and request limits rely on every worker seeing the same counts.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "phaema_cache",
    }
}

# Sessions: signed out after a working day at most, and after a period without using PHAEMA. Someone whose
# council account is closed therefore loses access within hours, not weeks.
SESSION_COOKIE_AGE = env.int("PHAEMA_SESSION_HOURS", default=10) * 3600
PHAEMA_IDLE_MINUTES = env.int("PHAEMA_IDLE_MINUTES", default=120)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# Wrong passwords allowed in the window before sign-in is paused, for one account and for one connection.
PHAEMA_SIGNIN_WINDOW_SECONDS = env.int("PHAEMA_SIGNIN_WINDOW_MINUTES", default=15) * 60
PHAEMA_SIGNIN_MAX_PER_ACCOUNT = env.int("PHAEMA_SIGNIN_MAX_PER_ACCOUNT", default=10)
PHAEMA_SIGNIN_MAX_PER_ADDRESS = env.int("PHAEMA_SIGNIN_MAX_PER_ADDRESS", default=50)

# Sign in with a username or an email address.
AUTHENTICATION_BACKENDS = ["apps.core.auth_backends.UsernameOrEmailBackend", "apps.connectors.sso.SsoBackend"]

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
    # Basic authentication (username and password) is refused for anyone with two-step sign-in, which a password
    # alone must not get round. They use the API from a signed-in browser session.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "apps.core.api_auth.PasswordOnlyBasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["apps.core.api_permissions.PhaemaPermission"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Request limits, on top of the limit on wrong passwords (which also covers the API).
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("PHAEMA_API_ANON_RATE", default="30/minute"),
        "user": env("PHAEMA_API_USER_RATE", default="1200/hour"),
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
# The release number: keep in step with the release tag on GitHub (v0.9.0 and so on).
PHAEMA_VERSION = "0.9.0"

SPECTACULAR_SETTINGS = {
    "TITLE": "PHAEMA API",
    "DESCRIPTION": "Property Holding and Estate Management Application: open API.",
    "VERSION": PHAEMA_VERSION,
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

# How long a "forgotten your password" link works for, in minutes.
PHAEMA_PASSWORD_RESET_MINUTES = env.int("PHAEMA_PASSWORD_RESET_MINUTES", default=60)

# Recognising text in scanned PDFs (OCR), on this server: Tesseract language codes joined with "+" (Welsh: eng+cym,
# with the tesseract-ocr-cym package), the largest document read, seconds allowed per page and pages read at once.
PHAEMA_OCR_LANGUAGES = env("PHAEMA_OCR_LANGUAGES", default="eng")
PHAEMA_OCR_MAX_PAGES = env.int("PHAEMA_OCR_MAX_PAGES", default=500)
PHAEMA_OCR_PAGE_SECONDS = env.int("PHAEMA_OCR_PAGE_SECONDS", default=180)
PHAEMA_OCR_JOBS = env.int("PHAEMA_OCR_JOBS", default=1)

# Name of the organisation shown in the header, e.g. "Example District Council".
PHAEMA_ORGANISATION_NAME = env("PHAEMA_ORGANISATION_NAME", default="Demonstration Council")
# A public test site holding only fictional data. Turns on the reset banner and allows ./phaema.sh reset-demo.
PHAEMA_DEMO_SITE = env.bool("PHAEMA_DEMO_SITE", default=False)
# Whether the council's "two-step sign-in required" setting is enforced. Leave on; the automated tests turn it off
# except where they test it.
PHAEMA_ENFORCE_TWO_STEP = env.bool("PHAEMA_ENFORCE_TWO_STEP", default=True)
PHAEMA_DEMO_RESET_HOURS = env.int("PHAEMA_DEMO_RESET_HOURS", default=48)
# Where requests for a test site sign-in are emailed (they are also listed under Manage data).
PHAEMA_ACCOUNT_REQUEST_EMAIL = env("PHAEMA_ACCOUNT_REQUEST_EMAIL", default="")

# Single sign-on with the council's own accounts (OpenID Connect): Microsoft Entra ID, Keycloak and others.
# Set by the installer; an administrator then turns it on in Module settings. Blank means off.
# For Microsoft 365 the issuer is https://login.microsoftonline.com/<tenant ID>/v2.0
PHAEMA_SSO_ISSUER = env("PHAEMA_SSO_ISSUER", default="")
PHAEMA_SSO_CLIENT_ID = env("PHAEMA_SSO_CLIENT_ID", default="")
PHAEMA_SSO_CLIENT_SECRET = env("PHAEMA_SSO_CLIENT_SECRET", default="")
# The name on the sign-in button: "Sign in with Microsoft".
PHAEMA_SSO_NAME = env("PHAEMA_SSO_NAME", default="Microsoft")
