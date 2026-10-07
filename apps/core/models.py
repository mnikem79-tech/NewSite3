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


class SortableModel(models.Model):
    """Ручной порядок вывода. Меньше число — выше в списке."""

    sort_order = models.IntegerField(
        _("порядок"),
        default=100,
        db_index=True,
        help_text=_("Меньше значение — выше в списке."),
    )

    class Meta:
        abstract = True


class SeoModel(models.Model):
    """SEO-поля. Если не заполнены — подставляются значения по умолчанию."""

    meta_title = models.CharField(
        _("SEO: заголовок"),
        max_length=255,
        blank=True,
        help_text=_("Пусто — берётся название."),
    )
    meta_description = models.CharField(
        _("SEO: описание"),
        max_length=500,
        blank=True,
        help_text=_("Рекомендуемая длина — до 160 символов."),
    )
    meta_keywords = models.CharField(_("SEO: ключевые слова"), max_length=255, blank=True)

    class Meta:
        abstract = True

    def get_meta_title(self) -> str:
        return self.meta_title or str(self)

    def get_meta_description(self) -> str:
        return self.meta_description
