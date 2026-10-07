"""
Заказы — ядро магазина.

Ключевое правило: позиция заказа хранит СНИМОК товара (название, артикул,
цена), а не только ссылку. Через год товар переименуют, подорожает или будет
удалён — заказ обязан выглядеть ровно так, как его оформил покупатель.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

ZERO = Decimal("0.00")


class OrderStatus(models.TextChoices):
    NEW = "new", _("Новый")
    CONFIRMED = "confirmed", _("Подтверждён")
    PACKED = "packed", _("Собран")
    SHIPPED = "shipped", _("Отправлен")
    DELIVERED = "delivered", _("Доставлен")
    CANCELLED = "cancelled", _("Отменён")
    REFUNDED = "refunded", _("Возврат")


# Разрешённые переходы. Держим в коде, а не в базе: логика переходов — часть
# продукта, и у всех установок дистрибутива она должна быть одинаковой.
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    OrderStatus.NEW: (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
    OrderStatus.CONFIRMED: (OrderStatus.PACKED, OrderStatus.CANCELLED),
    OrderStatus.PACKED: (OrderStatus.SHIPPED, OrderStatus.CANCELLED),
    OrderStatus.SHIPPED: (OrderStatus.DELIVERED, OrderStatus.REFUNDED),
    OrderStatus.DELIVERED: (OrderStatus.REFUNDED,),
    OrderStatus.CANCELLED: (),
    OrderStatus.REFUNDED: (),
}

# Статусы, при переходе в которые остаток возвращается на склад.
STOCK_RETURNING_STATUSES = (OrderStatus.CANCELLED, OrderStatus.REFUNDED)


class OrderQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED])

    def for_user(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(user=user)

    def with_items(self):
        return self.prefetch_related("items")


class Order(TimeStampedModel):
    """Заказ. Контактные данные копируются сюда на момент оформления."""

    number = models.CharField(_("номер"), max_length=32, unique=True, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("пользователь"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text=_("Пусто — заказ оформлен гостем."),
    )
    status = models.CharField(
        _("статус"),
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.NEW,
        db_index=True,
    )

    customer_name = models.CharField(_("имя покупателя"), max_length=255)
    email = models.EmailField(_("e-mail"))
    phone = models.CharField(_("телефон"), max_length=32)

    shipping_method = models.ForeignKey(
        "shipping.ShippingMethod",
        verbose_name=_("способ доставки"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
    )
    shipping_method_title = models.CharField(_("доставка (снимок)"), max_length=255, blank=True)
    shipping_address = models.TextField(_("адрес доставки"), blank=True)
    shipping_cost = models.DecimalField(
        _("стоимость доставки"), max_digits=12, decimal_places=2, default=ZERO
    )

    payment_method = models.ForeignKey(
        "payments.PaymentMethod",
        verbose_name=_("способ оплаты"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
    )
    payment_method_title = models.CharField(_("оплата (снимок)"), max_length=255, blank=True)

    subtotal = models.DecimalField(
        _("сумма товаров"), max_digits=12, decimal_places=2, default=ZERO
    )
    discount = models.DecimalField(_("скидка"), max_digits=12, decimal_places=2, default=ZERO)
    total = models.DecimalField(_("итого"), max_digits=12, decimal_places=2, default=ZERO)
    currency = models.CharField(_("валюта"), max_length=3, default="RUB")

    comment = models.TextField(_("комментарий покупателя"), blank=True)
    manager_note = models.TextField(
        _("заметка менеджера"), blank=True, help_text=_("Покупателю не видна.")
    )

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = _("заказ")
        verbose_name_plural = _("заказы")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return f"Заказ {self.number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Номер строим от первичного ключа: он уникален и уже выдан базой.
        # Генерировать «следующий свободный» вручную — гонка при параллельных
        # заказах, и рано или поздно два покупателя получат один номер.
        if not self.number:
            self.number = f"{timezone.now():%Y}-{self.pk:05d}"
            super().save(update_fields=["number"])

    def get_absolute_url(self):
        return reverse("orders:detail", kwargs={"number": self.number})

    @property
    def items_count(self) -> int:
        return sum(item.quantity for item in self.items.all())

    @property
    def is_paid(self) -> bool:
        return self.payments.filter(status="succeeded").exists()

    def can_change_to(self, new_status: str) -> bool:
        return new_status in ALLOWED_TRANSITIONS.get(self.status, ())

    def allowed_statuses(self) -> tuple[str, ...]:
        return ALLOWED_TRANSITIONS.get(self.status, ())

    def recalculate(self, save: bool = True):
        """Пересчёт сумм по позициям. Вызывается после правок в админке."""
        self.subtotal = sum((item.total for item in self.items.all()), ZERO)
        self.total = self.subtotal - self.discount + self.shipping_cost
        if save:
            self.save(update_fields=["subtotal", "total", "updated_at"])
        return self.total


class OrderItem(models.Model):
    """
    Позиция заказа — снимок товара на момент покупки.

    product задан как SET_NULL: удаление товара из каталога не должно
    уносить историю продаж.
    """

    order = models.ForeignKey(
        Order, verbose_name=_("заказ"), on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        "catalog.Product",
        verbose_name=_("товар"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )

    product_name = models.CharField(_("название"), max_length=255)
    product_sku = models.CharField(_("артикул"), max_length=64)
    price = models.DecimalField(_("цена за единицу"), max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(_("количество"), default=1)
    total = models.DecimalField(_("сумма"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("позиция заказа")
        verbose_name_plural = _("позиции заказа")
        ordering = ["pk"]

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"

    def save(self, *args, **kwargs):
        self.total = (self.price * self.quantity).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    """Кто, когда и на что поменял статус. Первый вопрос при любом разборе."""

    order = models.ForeignKey(
        Order, verbose_name=_("заказ"), on_delete=models.CASCADE, related_name="history"
    )
    from_status = models.CharField(_("из статуса"), max_length=20, blank=True)
    to_status = models.CharField(_("в статус"), max_length=20)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("кто изменил"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    comment = models.CharField(_("комментарий"), max_length=500, blank=True)
    created_at = models.DateTimeField(_("когда"), auto_now_add=True)

    class Meta:
        verbose_name = _("изменение статуса")
        verbose_name_plural = _("история статусов")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.number}: {self.from_status} → {self.to_status}"
