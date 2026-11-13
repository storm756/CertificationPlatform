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
    "unfold.contrib.import_export",
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
    "django_jsonform",
    "import_export",
    "rosetta",  # UI strings (.po) for staff translators (Stage 8)
    "apps.core",
    "apps.audit",
    "apps.accounts",
    "apps.batches",
    "apps.mentors",
    "apps.staff",
    "apps.content",
    "apps.questions",
    "apps.assessments",
    "apps.certificates",
    "apps.translations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "apps.accounts.middleware.ProfileLanguageMiddleware",
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
                "apps.core.context.programme",
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
# django-import-export: dry runs write inside a transaction that is rolled back.
IMPORT_EXPORT_USE_TRANSACTIONS = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Accounts ---
AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1
SITE_DOMAIN = env("SITE_DOMAIN", "localhost:8000")
# The programme name is read from here everywhere, never hard-coded (D23, D30).
PROGRAMME_NAME = "Community Cyber First Responder"
PROGRAMME_SHORT = "CCFR"
SITE_NAME = env("SITE_NAME", PROGRAMME_NAME)
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
MFA_TOTP_ISSUER = PROGRAMME_NAME

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
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", f"{PROGRAMME_NAME} <noreply@cyberfirstresponse.io>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- i18n ---
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("hi", "हिन्दी"), ("mr", "मराठी"), ("gu", "ગુજરાતી")]
# Our own catalogues. Django ships none for Gujarati, and without one it ignores "gu" entirely.
LOCALE_PATHS = [BASE_DIR / "locale"]

# Django lacks language info for Gujarati; without it the admin templates raise KeyError.
import django.conf.locale  # noqa: E402

django.conf.locale.LANG_INFO = {
    **django.conf.locale.LANG_INFO,
    "gu": {"bidi": False, "code": "gu", "name": "Gujarati", "name_local": "ગુજરાતી"},
}
# Rosetta edits the .po files of this checkout. On a server those edits are not kept across a
# deploy: download the catalogue from Rosetta and commit it in a PR (architecture §14).
ROSETTA_ACCESS_CONTROL_FUNCTION = "apps.translations.rules.can_use_rosetta"
ROSETTA_MESSAGES_SOURCE_LANGUAGE_CODE = "en"
ROSETTA_MESSAGES_SOURCE_LANGUAGE_NAME = "English"
ROSETTA_EXCLUDED_APPLICATIONS = ["rosetta", "unfold", "allauth", "simple_history", "import_export"]
ROSETTA_SHOW_AT_ADMIN_PANEL = True
ROSETTA_WSGI_AUTO_RELOAD = False
ROSETTA_UWSGI_AUTO_RELOAD = False
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static / media (Caddy serves /static from this volume) ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
# Behind Caddy, /learn/media/<id>/ answers with X-Accel-Redirect and Caddy sends the file with range
# requests (D35). Off in development and tests, where Django sends the file itself.
MEDIA_ACCEL_REDIRECT = env_bool("MEDIA_ACCEL_REDIRECT", False)

# --- Unfold admin ---
UNFOLD = {
    "SITE_TITLE": f"{PROGRAMME_SHORT} Admin",
    "SITE_HEADER": PROGRAMME_NAME,
    "DASHBOARD_CALLBACK": "apps.core.dashboard.dashboard_callback",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    # WeasyPrint and fontTools log every rendering step at INFO; keep only their warnings.
    "loggers": {
        "weasyprint": {"level": "WARNING"},
        "fontTools": {"level": "WARNING"},
    },
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
# An attempt with no save for this long is submitted with its saved answers (architecture 9.3).
STALE_ATTEMPT_DAYS = 7

# --- Certificates (architecture §12, D28, D36) ---
# Number: <prefix>-<issue year>-<batch centre code>-<6-digit serial from one global DB sequence>.
CERTIFICATE_PREFIX = "CCFR"
CERTIFICATE_DEFAULT_CENTRE = "SAKEC"  # a new batch's centre code; admins change it per batch
CERTIFICATE_QUALIFICATION = f"{PROGRAMME_NAME} ({PROGRAMME_SHORT})"
# Printed left to right. Signature images are never in git (D22, D36): each `image` is a file name
# in CERTIFICATE_PRIVATE_ROOT/signatures/ on the server. A missing image prints the name and
# designation over a blank signature line.
CERTIFICATE_SIGNATORIES = [
    {
        "name": "Dr. Nilakshi Jain",
        "designation": "HOD, Cyber Security Department",
        "organisation": "SAKEC",
        "image": "signature-1.png",
    },
    {
        "name": "Dr. Bhavesh Patel",
        "designation": "Principal",
        "organisation": "SAKEC",
        "image": "signature-2.png",
    },
    {
        "name": "Maj. Vineet Kumar",
        "designation": "Founder",
        "organisation": "CyberPeace Foundation",
        "image": "signature-3.png",
    },
]
# Issued PDFs (certificates/) and signature images (signatures/). Inside the media volume, so the
# nightly media backup covers them; nothing ever serves this folder directly (§16).
CERTIFICATE_PRIVATE_ROOT = Path(env("CERTIFICATE_PRIVATE_ROOT", str(MEDIA_ROOT / "private")))
# False while the certificate design and the CCFR emblem are placeholders. Mentors and admins see
# a warning before approving (each PDF is fixed at issue). A person turns it on with the final
# design.
CERTIFICATE_DESIGN_FINAL = False
CERTIFICATE_VERIFY_RATE = "30/10m"  # per client IP, on the public verify page
CERTIFICATE_APPROVE_PER_REQUEST = 15  # "Approve all" issues at most this many per click

# Daily jobs run by `manage.py run_periodic` (D27) at this Asia/Kolkata time (after the backup).
from datetime import time as _time  # noqa: E402

PERIODIC_RUN_AT = _time(3, 0)

# --- Public pages (Stage 9) ---
# "Who runs it" shows the three people with photos only after each has agreed to appear. Until then
# the landing page shows a placeholder card. Photos are never in git (D22): they live in
# content-data/people/ locally and in PEOPLE_PHOTO_DIR on the server.
PEOPLE_CONSENT_GIVEN = env_bool("PEOPLE_CONSENT_GIVEN", False)
PEOPLE_PHOTO_DIR = Path(env("PEOPLE_PHOTO_DIR", str(BASE_DIR / "content-data" / "people")))
