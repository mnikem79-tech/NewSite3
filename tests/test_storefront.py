"""Тесты витрины: страницы открываются, фильтры и поиск работают."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.catalog.models import Attribute, Category, Product, ProductAttribute


@pytest.fixture
def tree(db):
    root = Category.objects.create(name="Электроника", slug="electronics")
    child = Category.objects.create(name="Наушники", slug="headphones", parent=root)
    return root, child


@pytest.fixture
def products(tree):
    _root, child = tree
    cheap = Product.objects.create(
        category=child,
        name="Наушники Mini",
        slug="mini",
        sku="A-1",
        price=Decimal("2000"),
        stock=10,
    )
    pricey = Product.objects.create(
        category=child,
        name="Наушники Pro",
        slug="pro",
        sku="A-2",
        price=Decimal("9000"),
        old_price=Decimal("12000"),
        stock=0,
    )
    return cheap, pricey


@pytest.mark.django_db
def test_home_page(client, products):
    response = client.get(reverse("catalog:home"))
    assert response.status_code == 200
    assert "Электроника" in response.content.decode()


@pytest.mark.django_db
def test_category_shows_products_of_subtree(client, tree, products):
    root, _child = tree
    response = client.get(root.get_absolute_url())
    assert response.status_code == 200
    body = response.content.decode()
    # Товары лежат в подкатегории, но должны попасть в список родительской.
    assert "Наушники Mini" in body
    assert "Наушники Pro" in body


@pytest.mark.django_db
def test_in_stock_filter(client, tree, products):
    root, _child = tree
    response = client.get(root.get_absolute_url(), {"in_stock": "1"})
    body = response.content.decode()
    assert "Наушники Mini" in body
    assert "Наушники Pro" not in body


@pytest.mark.django_db
def test_price_filter(client, tree, products):
    root, _child = tree
    response = client.get(root.get_absolute_url(), {"price_max": "5000"})
    body = response.content.decode()
    assert "Наушники Mini" in body
    assert "Наушники Pro" not in body


@pytest.mark.django_db
def test_broken_price_filter_does_not_crash(client, tree, products):
    root, _child = tree
    response = client.get(root.get_absolute_url(), {"price_min": "дёшево"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_sorting_by_price(client, tree, products):
    root, _child = tree
    response = client.get(root.get_absolute_url(), {"sort": "-price"})
    skus = [p.sku for p in response.context["products"]]
    assert skus == ["A-2", "A-1"]


@pytest.mark.django_db
def test_attribute_facet_filter(client, tree, products):
    _root, child = tree
    cheap, pricey = products
    material = Attribute.objects.create(name="Материал", slug="material", is_filterable=True)
    ProductAttribute.objects.create(product=cheap, attribute=material, value="пластик")
    ProductAttribute.objects.create(product=pricey, attribute=material, value="металл")

    response = client.get(child.get_absolute_url(), {"attr-material": "металл"})
    skus = [p.sku for p in response.context["products"]]
    assert skus == ["A-2"]


@pytest.mark.django_db
def test_product_detail(client, products):
    cheap, _pricey = products
    response = client.get(cheap.get_absolute_url())
    assert response.status_code == 200
    assert "A-1" in response.content.decode()


@pytest.mark.django_db
def test_inactive_product_returns_404(client, products):
    cheap, _pricey = products
    cheap.is_active = False
    cheap.save()
    assert client.get(cheap.get_absolute_url()).status_code == 404


@pytest.mark.django_db
def test_search_finds_by_name(client, products):
    response = client.get(reverse("catalog:search"), {"q": "Mini"})
    assert "Наушники Mini" in response.content.decode()


@pytest.mark.django_db
def test_search_tolerates_typo(client, products):
    """pg_trgm должен вытянуть товар, несмотря на опечатку в запросе."""
    response = client.get(reverse("catalog:search"), {"q": "Наушники Minni"})
    assert response.status_code == 200
    assert response.context["fuzzy"] is True
    assert len(response.context["products"]) > 0


@pytest.mark.django_db
def test_empty_search(client, products):
    response = client.get(reverse("catalog:search"), {"q": ""})
    assert response.status_code == 200
    assert len(response.context["products"]) == 0
