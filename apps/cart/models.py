"""
Корзина.

Цена в корзине не хранится — считается от актуальной Product.price.
Покупатель всегда видит текущую цену, а не ту, что была месяц назад.
Фиксация происходит только в момент оформления заказа, в OrderItem.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

ZERO = Decimal("0.00")


class Cart(TimeStampedModel):
    """Корзина гостя (по ключу сессии) или пользователя."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("пользователь"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart",
    )
    session_key = models.CharField(_("ключ сессии"), max_length=64, blank=True, db_index=True)

    class Meta:
        verbose_name = _("корзина")
        verbose_name_plural = _("корзины")
        ordering = ["-updated_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | ~models.Q(session_key=""),
                name="cart_has_owner_or_session",
            )
        ]

    def __str__(self):
        owner = self.user.email if self.user_id else f"гость {self.session_key[:8]}"
        return f"Корзина ({owner})"

    @property
    def subtotal(self) -> Decimal:
        return sum((item.line_total for item in self.items.all()), ZERO)

    @property
    def count(self) -> int:
        return sum(item.quantity for item in self.items.all())

    @property
    def weight(self) -> Decimal:
        total = ZERO
        for item in self.items.all():
            if item.product.weight:
                total += item.product.weight * item.quantity
        return total

    @property
    def is_empty(self) -> bool:
        return not self.items.exists()

    def has_stock_problems(self) -> list[str]:
        """Список проблем: товар отключили или остатка не хватает."""
        problems = []
        for item in self.items.select_related("product"):
            product = item.product
            if not product.is_active:
                problems.append(f"«{product.name}» больше не продаётся")
            elif product.track_stock and product.stock < item.quantity:
                problems.append(
                    f"«{product.name}»: доступно {product.stock} шт., в корзине {item.quantity}"
                )
        return problems

    def clear(self):
        self.items.all().delete()


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, verbose_name=_("корзина"), on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        "catalog.Product",
        verbose_name=_("товар"),
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(_("количество"), default=1)

    class Meta:
        verbose_name = _("позиция корзины")
        verbose_name_plural = _("позиции корзины")
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="cart_unique_product"),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="cart_item_positive_quantity"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} × {self.quantity}"

    @property
    def line_total(self) -> Decimal:
        return (self.product.price * self.quantity).quantize(Decimal("0.01"))

    @property
    def max_quantity(self) -> int | None:
        """Сколько можно заказать. None — ограничения нет."""
        if not self.product.track_stock:
            return None
        return self.product.stock
