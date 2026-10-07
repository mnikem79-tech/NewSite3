"""
Оформление заказа и смена статусов.

Самое ответственное место магазина: здесь списываются остатки, фиксируются
цены и создаётся платёж. Всё выполняется в одной транзакции — либо заказ
создан целиком, либо не создан вовсе.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from apps.catalog.models import Product

from .models import ALLOWED_TRANSITIONS, STOCK_RETURNING_STATUSES, Order, OrderItem, OrderStatus

logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")


class OrderError(Exception):
    """Заказ оформить нельзя — причина в сообщении."""


@transaction.atomic
def create_order_from_cart(*, cart, data: dict, user=None) -> Order:
    """
    Превратить корзину в заказ.

    data: customer_name, email, phone, shipping_method, shipping_address,
          payment_method, comment
    """
    items = list(cart.items.select_related("product"))
    if not items:
        raise OrderError("Корзина пуста.")

    # Блокируем товары до конца транзакции. Без этого два параллельных заказа
    # последней единицы оба пройдут проверку остатка и уйдут в минус.
    product_ids = [item.product_id for item in items]
    locked = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=product_ids)
    }

    subtotal = ZERO
    weight = ZERO
    for item in items:
        product = locked.get(item.product_id)
        if product is None or not product.is_active:
            raise OrderError(f"«{item.product.name}» больше не продаётся.")
        if product.track_stock and product.stock < item.quantity:
            raise OrderError(
                f"«{product.name}»: в наличии {product.stock} шт., " f"а в корзине {item.quantity}."
            )
        subtotal += product.price * item.quantity
        if product.weight:
            weight += product.weight * item.quantity

    shipping_method = data.get("shipping_method")
    shipping_cost = shipping_method.calculate(subtotal, weight) if shipping_method else ZERO

    payment_method = data.get("payment_method")

    order = Order.objects.create(
        user=user if (user and user.is_authenticated) else None,
        customer_name=data["customer_name"],
        email=data["email"].lower(),
        phone=data["phone"],
        shipping_method=shipping_method,
        shipping_method_title=str(shipping_method) if shipping_method else "",
        shipping_address=data.get("shipping_address", ""),
        shipping_cost=shipping_cost,
        payment_method=payment_method,
        payment_method_title=str(payment_method) if payment_method else "",
        subtotal=subtotal.quantize(Decimal("0.01")),
        total=(subtotal + shipping_cost).quantize(Decimal("0.01")),
        comment=data.get("comment", ""),
        status=OrderStatus.NEW,
    )

    for item in items:
        product = locked[item.product_id]
        OrderItem.objects.create(
            order=order,
            product=product,
            # Снимок: название, артикул и цена фиксируются навсегда.
            product_name=product.name,
            product_sku=product.sku,
            price=product.price,
            quantity=item.quantity,
        )
        if product.track_stock:
            # F() вместо product.stock -= n: вычитает сама база, без гонок.
            Product.objects.filter(pk=product.pk).update(stock=F("stock") - item.quantity)

    order.history.create(to_status=OrderStatus.NEW, comment="Заказ создан")

    if payment_method:
        try:
            payment_method.get_provider().create_payment(order)
        except Exception:
            logger.exception("Не удалось создать платёж для заказа %s", order.number)
            raise

    cart.clear()
    logger.info("Создан заказ %s на сумму %s", order.number, order.total)
    return order


@transaction.atomic
def change_status(order: Order, new_status: str, *, user=None, comment: str = "") -> Order:
    """Смена статуса с проверкой перехода, записью истории и возвратом остатков."""
    if new_status == order.status:
        return order

    if new_status not in ALLOWED_TRANSITIONS.get(order.status, ()):
        allowed = ", ".join(ALLOWED_TRANSITIONS.get(order.status, ())) or "нет"
        raise ValidationError(
            f"Переход «{order.get_status_display()}» → «{new_status}» запрещён. "
            f"Допустимо: {allowed}."
        )

    previous = order.status
    order.status = new_status
    order.save(update_fields=["status", "updated_at"])

    if new_status in STOCK_RETURNING_STATUSES and previous not in STOCK_RETURNING_STATUSES:
        return_stock(order)

    order.history.create(from_status=previous, to_status=new_status, user=user, comment=comment)
    logger.info("Заказ %s: %s → %s", order.number, previous, new_status)
    return order


def return_stock(order: Order) -> None:
    """Вернуть остатки на склад при отмене или возврате."""
    for item in order.items.select_related("product"):
        if item.product and item.product.track_stock:
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
    logger.info("Остатки по заказу %s возвращены на склад", order.number)
