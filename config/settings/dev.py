"""Настройки для разработки на nail-srv."""

from .base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "nail-srv", "0.0.0.0"]

INTERNAL_IPS = ["127.0.0.1"]

# Письма печатаются в консоль, ничего наружу не уходит.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# На деве статика отдаётся без манифеста — иначе пришлось бы гонять
# collectstatic после каждой правки css.
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}

# Мягкие требования к паролю, чтобы не мучиться с тестовыми учётками.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 6},
    },
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # Раскомментируй, чтобы видеть все SQL-запросы:
        # "django.db.backends": {"level": "DEBUG", "handlers": ["console"],
        #                        "propagate": False},
    },
}
