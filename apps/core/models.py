"""Базовые абстрактные модели, от которых наследуются остальные приложения."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """Отметки создания и изменения. Нужны практически каждой сущности магазина."""

    created_at = models.DateTimeField(_("создано"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("изменено"), auto_now=True)

    class Meta:
        abstract = True


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class ActivatableModel(models.Model):
    """Мягкое отключение записи вместо удаления: ссылки в заказах не ломаются."""

    is_active = models.BooleanField(_("активно"), default=True, db_index=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        abstract = True
