"""
Платежи: способ оплаты и попытка оплаты.

Онлайн-провайдеров в коробке нет, но абстракция заложена сразу — тот, кто
поставит дистрибутив, почти наверняка подключит своего. Добавление ЮKassa
или Stripe = новый класс провайдера плюс запись в PaymentMethod,
без единой правки в приложении orders.
"""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ActivatableModel, SortableModel, TimeStampedModel


class PaymentMethod(SortableModel, ActivatableModel):
    """Способ оплаты, видимый покупателю на оформлении заказа."""

    class Provider(models.TextChoices):
        MANUAL = "manual", _("Без онлайн-оплаты (при получении / по счёту)")
        # Сюда добавляются провайдеры: YOOKASSA, STRIPE, ROBOKASSA...

    code = models.SlugField(_("код"), max_length=64, unique=True)
    title = models.CharField(_("название"), max_length=255)
    description = models.CharField(_("краткое описание"), max_length=500, blank=True)
    instructions = models.TextField(
        _("инструкция после заказа"),
        blank=True,
        help_text=_("Показывается покупателю на странице «спасибо» и в письме."),
    )
    provider = models.CharField(
        _("провайдер"),
        max_length=32,
        choices=Provider.choices,
        default=Provider.MANUAL,
    )
    config = models.JSONField(
        _("настройки провайдера"),
        default=dict,
        blank=True,
        help_text=_("Ключи API и прочее. У каждого провайдера свои поля."),
    )

    class Meta:
        verbose_name = _("способ оплаты")
        verbose_name_plural = _("способы оплаты")
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    def get_provider(self):
        from .providers import get_provider

        return get_provider(self)


class Payment(TimeStampedModel):
    """Попытка оплаты заказа. Одному заказу может соответствовать несколько."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Ожидает оплаты")
        SUCCEEDED = "succeeded", _("Оплачен")
        FAILED = "failed", _("Ошибка оплаты")
        REFUNDED = "refunded", _("Возврат")

    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("заказ"),
        on_delete=models.CASCADE,
        related_name="payments",
    )
    method = models.ForeignKey(
        PaymentMethod,
        verbose_name=_("способ оплаты"),
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(_("сумма"), max_digits=12, decimal_places=2)
    currency = models.CharField(_("валюта"), max_length=3, default="RUB")
    status = models.CharField(
        _("статус"), max_length=20, choices=Status.choices, default=Status.PENDING
    )
    external_id = models.CharField(
        _("идентификатор у провайдера"), max_length=255, blank=True, db_index=True
    )
    payload = models.JSONField(
        _("ответ провайдера"),
        default=dict,
        blank=True,
        help_text=_("Сырые данные. Нужны при разборе спорных платежей."),
    )
    paid_at = models.DateTimeField(_("оплачен"), null=True, blank=True)

    class Meta:
        verbose_name = _("платёж")
        verbose_name_plural = _("платежи")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.number} — {self.amount} {self.currency} ({self.get_status_display()})"

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.SUCCEEDED

    def mark_paid(self, external_id: str = "", payload: dict | None = None):
        from django.utils import timezone

        self.status = self.Status.SUCCEEDED
        self.paid_at = timezone.now()
        if external_id:
            self.external_id = external_id
        if payload:
            self.payload = payload
        self.save(update_fields=["status", "paid_at", "external_id", "payload", "updated_at"])


def default_currency() -> str:
    from django.conf import settings

    return getattr(settings, "DEFAULT_CURRENCY", "RUB")


def to_money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))
