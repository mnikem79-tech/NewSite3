"""Тесты каталога: правила, которые легко сломать при доработке."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from apps.catalog.models import Category, Product


@pytest.fixture
def category(db):
    return Category.objects.create(name="Электроника", slug="electronics")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Смартфон",
        slug="smartphone",
        sku="PHN-1",
        price=Decimal("1000.00"),
        stock=5,
    )


@pytest.mark.django_db
def test_in_stock_respects_track_stock(product):
    product.stock = 0
    assert product.in_stock is False

    product.track_stock = False
    assert product.in_stock is True


@pytest.mark.django_db
def test_discount_calculation(product):
    product.old_price = Decimal("1250.00")
    assert product.is_on_sale is True
    assert product.discount_percent == 20


@pytest.mark.django_db
def test_old_price_must_be_greater(product):
    product.old_price = Decimal("900.00")
    with pytest.raises(ValidationError):
        product.full_clean()


@pytest.mark.django_db
def test_old_price_constraint_in_database(category):
    """Проверка на уровне БД — на случай, если кто-то обойдёт full_clean()."""
    with pytest.raises(IntegrityError):
        Product.objects.create(
            category=category,
            name="Битый",
            slug="broken",
            sku="BRK-1",
            price=Decimal("1000.00"),
            old_price=Decimal("500.00"),
        )


@pytest.mark.django_db
def test_available_queryset(category):
    Product.objects.create(
        category=category, name="Есть", slug="a", sku="A", price=Decimal("10"), stock=5
    )
    Product.objects.create(
        category=category, name="Нет", slug="b", sku="B", price=Decimal("10"), stock=0
    )
    Product.objects.create(
        category=category,
        name="Без учёта",
        slug="c",
        sku="C",
        price=Decimal("10"),
        stock=0,
        track_stock=False,
    )
    Product.objects.create(
        category=category,
        name="Скрыт",
        slug="d",
        sku="D",
        price=Decimal("10"),
        stock=5,
        is_active=False,
    )

    assert set(Product.objects.available().values_list("sku", flat=True)) == {"A", "C"}


@pytest.mark.django_db
def test_category_cycle_is_rejected(category):
    child = Category.objects.create(name="Телефоны", slug="phones", parent=category)
    category.parent = child
    with pytest.raises(ValidationError):
        category.full_clean()


@pytest.mark.django_db
def test_descendant_ids_collects_subtree(category):
    child = Category.objects.create(name="Телефоны", slug="phones", parent=category)
    grandchild = Category.objects.create(name="Кнопочные", slug="basic", parent=child)

    ids = category.get_descendant_ids()
    assert set(ids) == {category.pk, child.pk, grandchild.pk}


@pytest.mark.django_db
def test_breadcrumb(category):
    child = Category.objects.create(name="Телефоны", slug="phones", parent=category)
    assert child.breadcrumb == "Электроника / Телефоны"


@pytest.mark.django_db
def test_category_with_products_cannot_be_deleted(product, category):
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        category.delete()
