"""Настройки только для демонстрации в песочнице. На сервер не ставятся."""

from .dev import *  # noqa: F403

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["https://*.e2b.app", "http://localhost:8000", "http://127.0.0.1:8000"]
