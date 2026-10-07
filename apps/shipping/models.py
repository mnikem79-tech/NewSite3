"""Способы доставки и расчёт её стоимости."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ActivatableModel, SortableModel

ZERO = Decimal("0.00")


class ShippingMethod(SortableModel, ActivatableModel):
    """
    Способ доставки с одной из трёх схем расчёта.

    Три схемы покрывают подавляющее большинство магазинов. Интеграции с
    конкретными службами (СДЭК, Почта) делаются отдельными провайдерами
    по образцу платежей — но это уже не в базовой коробке.
    """

    class Calculation(models.TextChoices):
        FIXED = "fixed", _("Фиксированная стоимость")
        FREE_FROM = "free_from", _("Бесплатно от суммы заказа")
        BY_WEIGHT = "by_weight", _("По весу заказа")

    code = models.SlugField(_("код"), max_length=64, unique=True)
    title = models.CharField(_("название"), max_length=255)
    description = models.CharField(_("описание"), max_length=500, blank=True)

    calculation = models.CharField(
        _("схема расчёта"),
        max_length=20,
        choices=Calculation.choices,
        default=Calculation.FIXED,
    )
    price = models.DecimalField(
        _("стоимость"),
        max_digits=12,
        decimal_places=2,
        default=ZERO,
        help_text=_("Для схемы «по весу» — стоимость базовой доставки."),
    )
    free_from_amount = models.DecimalField(
        _("бесплатно от суммы"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Только для схемы «бесплатно от суммы»."),
    )
    price_per_kg = models.DecimalField(
        _("доплата за кг"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Только для схемы «по весу»."),
    )
    requires_address = models.BooleanField(
        _("нужен адрес"),
        default=True,
        help_text=_("Снимите для самовывоза."),
    )

    class Meta:
        verbose_name = _("способ доставки")
        verbose_name_plural = _("способы доставки")
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.calculation == self.Calculation.FREE_FROM and self.free_from_amount is None:
            raise ValidationError({"free_from_amount": _("Для этой схемы нужно указать сумму.")})
        if self.calculation == self.Calculation.BY_WEIGHT and self.price_per_kg is None:
            raise ValidationError({"price_per_kg": _("Для этой схемы нужна доплата за кг.")})

    def calculate(self, subtotal: Decimal, weight: Decimal | None = None) -> Decimal:
        """Стоимость доставки для конкретного заказа."""
        subtotal = Decimal(subtotal or 0)

        if self.calculation == self.Calculation.FREE_FROM:
            if self.free_from_amount is not None and subtotal >= self.free_from_amount:
                return ZERO
            return self.price

        if self.calculation == self.Calculation.BY_WEIGHT:
            weight = Decimal(weight or 0)
            per_kg = self.price_per_kg or ZERO
            return (self.price + per_kg * weight).quantize(Decimal("0.01"))

        return self.price

    def describe(self, subtotal: Decimal, weight: Decimal | None = None) -> str:
        """Текст для страницы оформления — покупатель должен понимать, за что платит."""
        cost = self.calculate(subtotal, weight)
        if cost == ZERO:
            return _("бесплатно")
        return f"{cost:.0f} ₽"
