"""Счётчик корзины в шапке на каждой странице."""

from .services import get_cart


def cart(request):
    cart_obj = get_cart(request, create=False)
    return {
        "cart": cart_obj,
        "cart_count": cart_obj.count if cart_obj else 0,
    }
