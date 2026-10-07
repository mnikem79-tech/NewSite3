"""Представления корзины. Все изменения — только POST, чтобы их нельзя было
выполнить переходом по ссылке или предзагрузкой браузера."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from apps.catalog.models import Product

from .services import CartError, add_product, get_cart, remove_product, set_quantity


def _is_ajax(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _respond(request, redirect_to: str = "cart:detail"):
    cart = get_cart(request, create=False)
    if _is_ajax(request):
        return JsonResponse(
            {
                "count": cart.count if cart else 0,
                "subtotal": float(cart.subtotal) if cart else 0,
            }
        )
    return redirect(request.POST.get("next") or redirect_to)


class CartView(TemplateView):
    template_name = "cart/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart = get_cart(self.request, create=False)
        context["cart"] = cart
        context["items"] = (
            cart.items.select_related("product").prefetch_related("product__images") if cart else []
        )
        context["problems"] = cart.has_stock_problems() if cart else []
        return context


@require_POST
def add_to_cart(request, product_id: int):
    product = get_object_or_404(Product.objects.active(), pk=product_id)
    cart = get_cart(request)

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1

    try:
        add_product(cart, product, quantity)
        messages.success(request, f"«{product.name}» добавлен в корзину.")
    except CartError as exc:
        messages.error(request, str(exc))

    return _respond(request, redirect_to=product.get_absolute_url())


@require_POST
def update_quantity(request, product_id: int):
    product = get_object_or_404(Product, pk=product_id)
    cart = get_cart(request)

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1

    try:
        set_quantity(cart, product, quantity)
    except CartError as exc:
        messages.warning(request, str(exc))

    return _respond(request)


@require_POST
def remove_from_cart(request, product_id: int):
    product = get_object_or_404(Product, pk=product_id)
    cart = get_cart(request, create=False)
    if cart:
        remove_product(cart, product)
        messages.info(request, f"«{product.name}» убран из корзины.")
    return _respond(request)
