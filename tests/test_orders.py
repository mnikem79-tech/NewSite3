"""Тесты оформления заказа — самая ответственная часть магазина."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.cart.models import Cart
from apps.cart.services import add_product
from apps.catalog.models import Category, Product
from apps.orders.models import Order, OrderStatus
from apps.orders.services import OrderError, change_status, create_order_from_cart
from apps.payments.models import Payment, PaymentMethod
from apps.shipping.models import ShippingMethod

User = get_user_model()


@pytest.fixture
def category(db):
    return Category.objects.create(name="Тест", slug="test")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Товар",
        slug="tovar",
        sku="T-1",
        price=Decimal("1000.00"),
        stock=10,
        weight=Decimal("2.000"),
    )


@pytest.fixture
def shipping(db):
    return ShippingMethod.objects.create(
        code="courier",
        title="Курьер",
        calculation=ShippingMethod.Calculation.FREE_FROM,
        price=Decimal("350.00"),
        free_from_amount=Decimal("5000.00"),
    )


@pytest.fixture
def payment_method(db):
    return PaymentMethod.objects.create(
        code="on-delivery",
        title="При получении",
        provider=PaymentMethod.Provider.MANUAL,
    )


@pytest.fixture
def cart_with_item(product):
    cart = Cart.objects.create(session_key="s1")
    add_product(cart, product, 2)
    return cart


def order_data(shipping, payment_method, **overrides):
    data = {
        "customer_name": "Иван Иванов",
        "email": "ivan@example.com",
        "phone": "+7 900 000-00-00",
        "shipping_method": shipping,
        "shipping_address": "Москва, ул. Ленина, 1",
        "payment_method": payment_method,
        "comment": "",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------- создание
@pytest.mark.django_db
def test_order_snapshots_product_data(cart_with_item, shipping, payment_method, product):
    """Ключевое правило: позиция хранит снимок, а не ссылку на текущие данные."""
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))

    product.name = "Переименованный"
    product.price = Decimal("9999.00")
    product.save()

    item = order.items.first()
    assert item.product_name == "Товар"
    assert item.price == Decimal("1000.00")
    assert item.total == Decimal("2000.00")


@pytest.mark.django_db
def test_order_survives_product_deletion(cart_with_item, shipping, payment_method, product):
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    product.order_items.update(product=None)
    product.cart_items.all().delete()
    product.delete()

    order.refresh_from_db()
    item = order.items.first()
    assert item.product_name == "Товар"
    assert item.product_id is None


@pytest.mark.django_db
def test_stock_decremented(cart_with_item, shipping, payment_method, product):
    create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    product.refresh_from_db()
    assert product.stock == 8


@pytest.mark.django_db
def test_cart_cleared_after_order(cart_with_item, shipping, payment_method):
    create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    assert cart_with_item.items.count() == 0


@pytest.mark.django_db
def test_order_rejected_when_stock_insufficient(cart_with_item, shipping, payment_method, product):
    product.stock = 1
    product.save()
    with pytest.raises(OrderError):
        create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))


@pytest.mark.django_db
def test_failed_order_does_not_change_stock(cart_with_item, shipping, payment_method, product):
    """Транзакция: если заказ не создан, остаток не тронут."""
    product.stock = 1
    product.save()
    with pytest.raises(OrderError):
        create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    product.refresh_from_db()
    assert product.stock == 1
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_empty_cart_rejected(shipping, payment_method):
    empty = Cart.objects.create(session_key="empty")
    with pytest.raises(OrderError):
        create_order_from_cart(cart=empty, data=order_data(shipping, payment_method))


@pytest.mark.django_db
def test_order_number_is_unique_and_readable(cart_with_item, shipping, payment_method, product):
    first = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))

    second_cart = Cart.objects.create(session_key="s2")
    add_product(second_cart, product, 1)
    second = create_order_from_cart(cart=second_cart, data=order_data(shipping, payment_method))

    assert first.number != second.number
    assert first.number.startswith("20")
    assert len(first.number) == 10  # ГГГГ-NNNNN


@pytest.mark.django_db
def test_payment_created(cart_with_item, shipping, payment_method):
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    payment = Payment.objects.get(order=order)
    assert payment.status == Payment.Status.PENDING
    assert payment.amount == order.total


@pytest.mark.django_db
def test_history_recorded_on_creation(cart_with_item, shipping, payment_method):
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    assert order.history.count() == 1
    assert order.history.first().to_status == OrderStatus.NEW


# ---------------------------------------------------------------- доставка
@pytest.mark.django_db
def test_shipping_free_from_amount(cart_with_item, shipping, payment_method):
    """2 × 1000 = 2000 < 5000 → доставка платная."""
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    assert order.shipping_cost == Decimal("350.00")
    assert order.total == Decimal("2350.00")


@pytest.mark.django_db
def test_shipping_becomes_free(product, shipping, payment_method):
    cart = Cart.objects.create(session_key="big")
    add_product(cart, product, 6)  # 6000 >= 5000
    order = create_order_from_cart(cart=cart, data=order_data(shipping, payment_method))
    assert order.shipping_cost == Decimal("0.00")
    assert order.total == Decimal("6000.00")


@pytest.mark.django_db
def test_shipping_by_weight(product, payment_method):
    method = ShippingMethod.objects.create(
        code="post",
        title="Почта",
        calculation=ShippingMethod.Calculation.BY_WEIGHT,
        price=Decimal("250.00"),
        price_per_kg=Decimal("80.00"),
    )
    cart = Cart.objects.create(session_key="w")
    add_product(cart, product, 2)  # 2 шт × 2 кг = 4 кг
    order = create_order_from_cart(cart=cart, data=order_data(method, payment_method))
    assert order.shipping_cost == Decimal("570.00")  # 250 + 80 × 4


# ---------------------------------------------------------------- статусы
@pytest.mark.django_db
def test_valid_status_transition(cart_with_item, shipping, payment_method):
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    change_status(order, OrderStatus.CONFIRMED)
    assert order.status == OrderStatus.CONFIRMED
    assert order.history.count() == 2


@pytest.mark.django_db
def test_invalid_status_transition_rejected(cart_with_item, shipping, payment_method):
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    with pytest.raises(ValidationError):
        change_status(order, OrderStatus.DELIVERED)  # нельзя из «новый» сразу в «доставлен»


@pytest.mark.django_db
def test_cancel_returns_stock(cart_with_item, shipping, payment_method, product):
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    product.refresh_from_db()
    assert product.stock == 8

    change_status(order, OrderStatus.CANCELLED)
    product.refresh_from_db()
    assert product.stock == 10


@pytest.mark.django_db
def test_stock_returned_only_once(cart_with_item, shipping, payment_method, product):
    order = create_order_from_cart(cart=cart_with_item, data=order_data(shipping, payment_method))
    change_status(order, OrderStatus.CANCELLED)
    with pytest.raises(ValidationError):
        change_status(order, OrderStatus.REFUNDED)  # из «отменён» переходов нет
    product.refresh_from_db()
    assert product.stock == 10


# ---------------------------------------------------------------- вьюхи
@pytest.mark.django_db
def test_checkout_flow(client, product, shipping, payment_method):
    client.post(reverse("cart:add", args=[product.pk]), {"quantity": 1})

    response = client.get(reverse("orders:checkout"))
    assert response.status_code == 200

    response = client.post(
        reverse("orders:checkout"),
        {
            "customer_name": "Иван Иванов",
            "email": "Ivan@Example.COM",
            "phone": "+7 900 000-00-00",
            "shipping_method": shipping.pk,
            "shipping_address": "Москва, Ленина 1",
            "payment_method": payment_method.pk,
            "comment": "побыстрее",
        },
    )
    assert response.status_code == 302

    order = Order.objects.get()
    assert order.email == "ivan@example.com"  # приведён к нижнему регистру
    assert order.items.count() == 1
    assert len(mail.outbox) == 1
    assert order.number in mail.outbox[0].subject


@pytest.mark.django_db
def test_checkout_requires_address_for_courier(client, product, shipping, payment_method):
    client.post(reverse("cart:add", args=[product.pk]), {"quantity": 1})
    response = client.post(
        reverse("orders:checkout"),
        {
            "customer_name": "Иван",
            "email": "i@e.com",
            "phone": "+79000000000",
            "shipping_method": shipping.pk,
            "shipping_address": "",
            "payment_method": payment_method.pk,
        },
    )
    assert response.status_code == 200
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_pickup_does_not_require_address(client, product, payment_method):
    pickup = ShippingMethod.objects.create(
        code="pickup", title="Самовывоз", price=Decimal("0"), requires_address=False
    )
    client.post(reverse("cart:add", args=[product.pk]), {"quantity": 1})
    response = client.post(
        reverse("orders:checkout"),
        {
            "customer_name": "Иван",
            "email": "i@e.com",
            "phone": "+79000000000",
            "shipping_method": pickup.pk,
            "shipping_address": "",
            "payment_method": payment_method.pk,
        },
    )
    assert response.status_code == 302
    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_invalid_phone_rejected(client, product, shipping, payment_method):
    client.post(reverse("cart:add", args=[product.pk]), {"quantity": 1})
    response = client.post(
        reverse("orders:checkout"),
        {
            "customer_name": "Иван",
            "email": "i@e.com",
            "phone": "нет",
            "shipping_method": shipping.pk,
            "shipping_address": "адрес",
            "payment_method": payment_method.pk,
        },
    )
    assert response.status_code == 200
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_checkout_with_empty_cart_redirects(client):
    response = client.get(reverse("orders:checkout"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_guest_can_open_own_order_but_not_others(client, product, shipping, payment_method):
    client.post(reverse("cart:add", args=[product.pk]), {"quantity": 1})
    client.post(
        reverse("orders:checkout"),
        {
            "customer_name": "Иван",
            "email": "i@e.com",
            "phone": "+79000000000",
            "shipping_method": shipping.pk,
            "shipping_address": "адрес",
            "payment_method": payment_method.pk,
        },
    )
    order = Order.objects.get()
    assert client.get(order.get_absolute_url()).status_code == 200

    # Другой посетитель тот же заказ открыть не должен.
    from django.test import Client

    assert Client().get(order.get_absolute_url()).status_code == 404
