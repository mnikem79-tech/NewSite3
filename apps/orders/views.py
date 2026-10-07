"""Оформление заказа и просмотр результата."""

import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, View

from apps.cart.services import get_cart

from .emails import send_order_confirmation
from .forms import CheckoutForm
from .models import Order
from .services import OrderError, create_order_from_cart

logger = logging.getLogger(__name__)

# Ключ сессии, дающий гостю доступ к только что оформленному заказу.
SESSION_ORDERS_KEY = "guest_orders"


class CheckoutView(View):
    template_name = "orders/checkout.html"

    def get_context(self, request, form):
        cart = get_cart(request, create=False)
        return {
            "form": form,
            "cart": cart,
            "items": cart.items.select_related("product") if cart else [],
            "problems": cart.has_stock_problems() if cart else [],
        }

    def get(self, request):
        cart = get_cart(request, create=False)
        if cart is None or cart.is_empty:
            messages.info(request, "Корзина пуста — нечего оформлять.")
            return redirect("cart:detail")

        initial = {}
        if request.user.is_authenticated:
            initial = {
                "customer_name": request.user.get_full_name(),
                "email": request.user.email,
                "phone": getattr(request.user, "phone", ""),
            }
        return render(
            request, self.template_name, self.get_context(request, CheckoutForm(initial=initial))
        )

    def post(self, request):
        cart = get_cart(request, create=False)
        if cart is None or cart.is_empty:
            return redirect("cart:detail")

        form = CheckoutForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self.get_context(request, form))

        try:
            order = create_order_from_cart(cart=cart, data=form.cleaned_data, user=request.user)
        except OrderError as exc:
            # Остаток мог закончиться, пока человек заполнял форму.
            messages.error(request, str(exc))
            return render(request, self.template_name, self.get_context(request, form))

        # Гостю выдаём доступ к его заказу через сессию: без этого он не
        # сможет открыть страницу «спасибо» после перезагрузки.
        guest_orders = request.session.get(SESSION_ORDERS_KEY, [])
        guest_orders.append(order.number)
        request.session[SESSION_ORDERS_KEY] = guest_orders[-20:]

        send_order_confirmation(order)
        return redirect(reverse("orders:success", kwargs={"number": order.number}))


class OrderSuccessView(DetailView):
    template_name = "orders/success.html"
    context_object_name = "order"
    slug_field = "number"
    slug_url_kwarg = "number"

    def get_queryset(self):
        return Order.objects.with_items().select_related("payment_method", "shipping_method")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payment = self.object.payments.select_related("method").first()
        context["payment"] = payment
        if payment:
            context["instructions"] = payment.method.get_provider().get_instructions(payment)
        return context


class OrderDetailView(OrderSuccessView):
    """То же, но с проверкой прав: чужой заказ открыть нельзя."""

    template_name = "orders/detail.html"

    def get_object(self, queryset=None):
        order = get_object_or_404(self.get_queryset(), number=self.kwargs["number"])
        user = self.request.user

        if user.is_authenticated and (order.user_id == user.pk or user.is_staff):
            return order
        if order.number in self.request.session.get(SESSION_ORDERS_KEY, []):
            return order

        from django.http import Http404

        raise Http404("Заказ не найден")


class OrderListView(ListView):
    """Личный кабинет: список заказов пользователя."""

    template_name = "orders/list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        return Order.objects.for_user(self.request.user).with_items()
