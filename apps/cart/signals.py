"""Слияние гостевой корзины с корзиной пользователя при входе."""

import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Cart
from .services import SESSION_CART_KEY, get_session_cart, merge_carts

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def merge_cart_on_login(sender, request, user, **kwargs):
    """
    Товары, набранные до входа, не должны пропадать.

    Гостевую корзину ищем по номеру в данных сессии: к этому моменту Django
    уже выполнил cycle_key(), и старого ключа сессии попросту не существует.
    """
    session_cart = get_session_cart(request)
    if session_cart is None:
        return

    user_cart = Cart.objects.filter(user=user).first()

    if user_cart is None:
        # Корзины у пользователя не было — просто закрепляем гостевую за ним.
        session_cart.user = user
        session_cart.session_key = ""
        session_cart.save(update_fields=["user", "session_key"])
        logger.info("Гостевая корзина #%s закреплена за %s", session_cart.pk, user)
    else:
        merge_carts(session_cart, user_cart)
        logger.info("Корзины объединены для %s", user)

    request.session.pop(SESSION_CART_KEY, None)
