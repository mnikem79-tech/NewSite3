"""Тесты корзины: поведение, которое легко сломать."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.cart.models import Cart
from apps.cart.services import CartError, add_product, merge_carts, set_quantity
from apps.catalog.models import Category, Product

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
        price=Decimal("100.00"),
        stock=10,
    )


@pytest.fixture
def cart(db):
    return Cart.objects.create(session_key="testsession")


@pytest.mark.django_db
def test_add_product(cart, product):
    add_product(cart, product, 2)
    assert cart.count == 2
    assert cart.subtotal == Decimal("200.00")


@pytest.mark.django_db
def test_add_same_product_twice_increases_quantity(cart, product):
    add_product(cart, product, 2)
    add_product(cart, product, 3)
    assert cart.items.count() == 1
    assert cart.count == 5


@pytest.mark.django_db
def test_cannot_add_more_than_stock(cart, product):
    add_product(cart, product, 999)
    assert cart.count == 10  # обрезано до остатка


@pytest.mark.django_db
def test_cannot_add_out_of_stock(cart, product):
    product.stock = 0
    product.save()
    with pytest.raises(CartError):
        add_product(cart, product, 1)


@pytest.mark.django_db
def test_untracked_product_has_no_limit(cart, product):
    product.track_stock = False
    product.stock = 0
    product.save()
    add_product(cart, product, 50)
    assert cart.count == 50


@pytest.mark.django_db
def test_set_quantity_zero_removes_item(cart, product):
    add_product(cart, product, 3)
    set_quantity(cart, product, 0)
    assert cart.items.count() == 0


@pytest.mark.django_db
def test_cart_detects_stock_problems(cart, product):
    add_product(cart, product, 5)
    product.stock = 2
    product.save()
    problems = cart.has_stock_problems()
    assert len(problems) == 1
    assert "доступно 2" in problems[0]


@pytest.mark.django_db
def test_merge_carts_sums_quantities(product, category):
    guest = Cart.objects.create(session_key="guest")
    user = User.objects.create_user(email="u@example.com", password="secret123")
    owner = Cart.objects.create(user=user)

    add_product(guest, product, 2)
    add_product(owner, product, 3)

    merge_carts(guest, owner)

    assert owner.items.count() == 1
    assert owner.count == 5
    assert not Cart.objects.filter(pk=guest.pk).exists()


@pytest.mark.django_db
def test_cart_merged_on_login(client, product):
    """Самое ценное: товары, набранные до входа, не теряются."""
    client.post(reverse("cart:add", args=[product.pk]), {"quantity": 2})
    User.objects.create_user(email="u@example.com", password="secret123")

    client.login(username="u@example.com", password="secret123")

    user_cart = Cart.objects.get(user__email="u@example.com")
    assert user_cart.count == 2


@pytest.mark.django_db
def test_add_via_view(client, product):
    response = client.post(reverse("cart:add", args=[product.pk]), {"quantity": 3})
    assert response.status_code == 302
    cart = Cart.objects.first()
    assert cart.count == 3


@pytest.mark.django_db
def test_get_requests_do_not_modify_cart(client, product):
    """Изменения только через POST: иначе предзагрузка ссылок браузером
    или поисковый робот наполнят корзину сами."""
    response = client.get(reverse("cart:add", args=[product.pk]))
    assert response.status_code == 405
    assert Cart.objects.count() == 0


@pytest.mark.django_db
def test_cart_page(client, product):
    client.post(reverse("cart:add", args=[product.pk]), {"quantity": 1})
    response = client.get(reverse("cart:detail"))
    assert response.status_code == 200
    assert "Товар" in response.content.decode()
