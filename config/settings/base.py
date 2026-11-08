"""Settings shared by every environment. Everything environment-specific comes from env vars."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "unfold",  # must come before django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "simple_history",
    "apps.core",
    "apps.audit",
    "apps.accounts",
    "apps.batches",
    "apps.mentors",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "apps.accounts.middleware.StaffMFARequiredMiddleware",
    "apps.accounts.middleware.LearnerGateMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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
            ],
        },
    },
]

# --- Database: the runtime user is csfr_app; migrations run with DB_USER=csfr_owner ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "csfr"),
        "USER": env("DB_USER", "csfr_app"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", "db"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Accounts ---
AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1
SITE_DOMAIN = env("SITE_DOMAIN", "localhost:8000")
SITE_NAME = env("SITE_NAME", "Cyber First Response")
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_ADAPTER = "apps.accounts.adapter.BudgetedAccountAdapter"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
LOGIN_REDIRECT_URL = "start"
LOGIN_URL = "account_login"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"

MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "Cyber First Response"

# Sessions (architecture 7.4): 14 days; staff are cut to 12 hours by the MFA middleware.
SESSION_COOKIE_AGE = 14 * 24 * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
STAFF_SESSION_AGE = 12 * 3600

# --- Email ---
EMAIL_HOST = env("EMAIL_HOST", "mailpit")
EMAIL_PORT = int(env("EMAIL_PORT", "1025"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", "Cyber First Response <noreply@cyberfirstresponse.io>"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- i18n ---
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("hi", "हिन्दी"), ("mr", "मराठी"), ("gu", "ગુજરાતી")]

# Django lacks language info for Gujarati; without it the admin templates raise KeyError.
import django.conf.locale  # noqa: E402

django.conf.locale.LANG_INFO = {
    **django.conf.locale.LANG_INFO,
    "gu": {"bidi": False, "code": "gu", "name": "Gujarati", "name_local": "ગુજરાતી"},
}
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static / media (Caddy serves /static from this volume) ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

# --- Unfold admin ---
UNFOLD = {
    "SITE_TITLE": "CSFR Admin",
    "SITE_HEADER": "Cyber First Response",
    "DASHBOARD_CALLBACK": "apps.core.dashboard.dashboard_callback",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

# --- Registration and email budgets (architecture 7.2, 7.3) ---
# Fold Gmail dots / +tags so one person can't register twice. On in prod, off on staging.
EMAIL_NORMALISE_ALIASES = env_bool("EMAIL_NORMALISE_ALIASES", False)
PRIVACY_NOTICE_VERSION = "1"
REGISTER_RATE = "30/10m"  # per batch, not per IP
GUARDIAN_LINK_DAYS = 14
EMAIL_DAILY_BUDGET = {"registration": 150, "reset_guardian": 100, "reserve": 50}
EMAIL_ALERT_AT = 150
UNVERIFIED_ACCOUNT_DAYS = 7
