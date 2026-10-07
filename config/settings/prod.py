"""
Настройки для продакшна.

Применяются автоустановщиком: DJANGO_SETTINGS_MODULE=config.settings.prod
"""

from .base import *  # noqa: F403

DEBUG = False

# Пустой список недопустим — установщик обязан прописать домен в .env.
if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("DJANGO_ALLOWED_HOSTS не задан в .env — продакшн запускать нельзя")

# ---------------------------------------------------------------- HTTPS
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# HSTS включаем только после того, как сертификат реально выпущен,
# иначе браузер запомнит https и сайт станет недоступен при откате.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# По умолчанию доверяем тем же доменам, что в ALLOWED_HOSTS. Переопределить
# нужно, если домен отвечает на нестандартном порту или используется www-алиас:
# CSRF_TRUSTED_ORIGINS=https://nail-app.ru,https://www.nail-app.ru
CSRF_TRUSTED_ORIGINS = env.list(  # noqa: F405
    "CSRF_TRUSTED_ORIGINS",
    default=[f"https://{h}" for h in ALLOWED_HOSTS if not h[0].isdigit()],  # noqa: F405
)

# ---------------------------------------------------------------- логи
LOG_DIR = BASE_DIR / "logs"  # noqa: F405
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {process:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "django.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "mail_admins": {
            "class": "django.utils.log.AdminEmailHandler",
            "level": "ERROR",
        },
    },
    "root": {"handlers": ["file"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["file", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------- прочее
ADMINS = [("admin", env("ADMIN_EMAIL", default=DEFAULT_FROM_EMAIL))]  # noqa: F405
MANAGERS = ADMINS
