"""
Работа с корзиной: получение, слияние при входе, изменение состава.

Вся логика собрана здесь, чтобы views оставались тонкими, а правила
(сколько можно добавить, что делать при входе) существовали в одном месте.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.catalog.models import Product

from .models import Cart, CartItem

logger = logging.getLogger(__name__)

MAX_QUANTITY_PER_ITEM = 999


class CartError(Exception):
    """Операция с корзиной невозможна — причина в сообщении."""


SESSION_CART_KEY = "cart_id"


def _ensure_session(request) -> str:
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def get_cart(request, create: bool = True) -> Cart | None:
    """
    Корзина текущего посетителя.

    Гостевая корзина адресуется номером в данных сессии, а не ключом сессии.
    Это принципиально: при входе Django вызывает ``cycle_key()`` и ключ
    сессии меняется, а содержимое переносится. Привязка к ключу означала бы
    потерю набранной корзины ровно в момент авторизации.
    """
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart is None and create:
            cart = Cart.objects.create(user=request.user, session_key="")
        return cart

    cart_id = request.session.get(SESSION_CART_KEY)
    if cart_id:
        cart = Cart.objects.filter(pk=cart_id, user__isnull=True).first()
        if cart is not None:
            return cart
        # Корзину удалили (слияние, чистка старых) — ссылка протухла.
        request.session.pop(SESSION_CART_KEY, None)

    if not create:
        return None

    cart = Cart.objects.create(session_key=_ensure_session(request))
    request.session[SESSION_CART_KEY] = cart.pk
    return cart


def get_session_cart(request) -> Cart | None:
    """Гостевая корзина сессии — нужна при входе, когда user уже подменён."""
    cart_id = request.session.get(SESSION_CART_KEY)
    if not cart_id:
        return None
    return Cart.objects.filter(pk=cart_id, user__isnull=True).first()


@transaction.atomic
def merge_carts(session_cart: Cart, user_cart: Cart) -> Cart:
    """
    Слияние гостевой корзины с корзиной пользователя при входе.

    Количества складываются. Потерять товары, которые человек набрал до
    авторизации, — верный способ потерять и заказ.
    """
    for item in session_cart.items.select_related("product"):
        existing = user_cart.items.filter(product=item.product).first()
        if existing:
            existing.quantity = min(existing.quantity + item.quantity, MAX_QUANTITY_PER_ITEM)
            existing.save(update_fields=["quantity"])
        else:
            item.cart = user_cart
            item.save(update_fields=["cart"])
    session_cart.delete()
    return user_cart


def add_product(cart: Cart, product: Product, quantity: int = 1) -> CartItem:
    """Добавить товар. Повторное добавление увеличивает количество."""
    if quantity < 1:
        raise CartError("Количество должно быть больше нуля.")
    if not product.is_active:
        raise CartError("Товар недоступен для заказа.")

    item = cart.items.filter(product=product).first()
    new_quantity = (item.quantity if item else 0) + quantity
    new_quantity = min(new_quantity, MAX_QUANTITY_PER_ITEM)

    if product.track_stock and new_quantity > product.stock:
        if product.stock == 0:
            raise CartError(f"«{product.name}» закончился.")
        new_quantity = product.stock

    if item:
        item.quantity = new_quantity
        item.save(update_fields=["quantity"])
    else:
        item = cart.items.create(product=product, quantity=new_quantity)

    cart.save(update_fields=["updated_at"])
    return item


def set_quantity(cart: Cart, product: Product, quantity: int) -> CartItem | None:
    """Установить количество. Ноль и меньше — удалить позицию."""
    if quantity <= 0:
        remove_product(cart, product)
        return None

    quantity = min(quantity, MAX_QUANTITY_PER_ITEM)
    if product.track_stock and quantity > product.stock:
        quantity = max(product.stock, 0)
        if quantity == 0:
            remove_product(cart, product)
            raise CartError(f"«{product.name}» закончился и убран из корзины.")

    item, _created = cart.items.get_or_create(product=product, defaults={"quantity": quantity})
    if not _created:
        item.quantity = quantity
        item.save(update_fields=["quantity"])
    cart.save(update_fields=["updated_at"])
    return item


def remove_product(cart: Cart, product: Product) -> None:
    cart.items.filter(product=product).delete()
    cart.save(update_fields=["updated_at"])
