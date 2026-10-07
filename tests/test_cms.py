"""Тесты конструктора сайта."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.cms.models import ContentBlock, MenuItem, Page, SiteSettings

User = get_user_model()


@pytest.fixture
def page(db):
    return Page.objects.create(title="О компании", slug="about")


# ------------------------------------------------------------- настройки
@pytest.mark.django_db
def test_settings_are_singleton():
    first = SiteSettings.load()
    second = SiteSettings.load()
    assert first.pk == second.pk == 1
    assert SiteSettings.objects.count() == 1


@pytest.mark.django_db
def test_settings_cannot_be_duplicated():
    SiteSettings.load()
    extra = SiteSettings(site_name="Второй")
    extra.save()
    assert SiteSettings.objects.count() == 1
    assert SiteSettings.load().site_name == "Второй"


@pytest.mark.django_db
def test_settings_cannot_be_deleted():
    obj = SiteSettings.load()
    with pytest.raises(ValidationError):
        obj.delete()


@pytest.mark.django_db
def test_socials_skips_empty_fields():
    obj = SiteSettings.load()
    obj.telegram_url = "https://t.me/example"
    obj.save()
    assert [s["title"] for s in obj.socials] == ["Telegram"]


@pytest.mark.django_db
def test_settings_appear_on_every_page(client):
    obj = SiteSettings.load()
    obj.site_name = "Моя Лавка"
    obj.phone = "+7 999 111-22-33"
    obj.save()

    html = client.get(reverse("catalog:home")).content.decode()
    assert "Моя Лавка" in html
    assert "+7 999 111-22-33" in html


# -------------------------------------------------------------- страницы
@pytest.mark.django_db
def test_page_is_shown(client, page):
    ContentBlock.objects.create(page=page, kind="text", content="Мы продаём товары.")
    response = client.get(page.get_absolute_url())
    assert response.status_code == 200
    assert "Мы продаём товары." in response.content.decode()


@pytest.mark.django_db
def test_draft_hidden_from_visitors(client, page):
    page.is_active = False
    page.save()
    assert client.get(page.get_absolute_url()).status_code == 404


@pytest.mark.django_db
def test_draft_visible_to_staff(client, page):
    page.is_active = False
    page.save()
    User.objects.create_user(email="s@e.com", password="pass12345", is_staff=True)
    client.login(username="s@e.com", password="pass12345")

    response = client.get(page.get_absolute_url())
    assert response.status_code == 200
    assert "Черновик" in response.content.decode()


@pytest.mark.django_db
def test_reserved_slug_rejected():
    """Страница со slug «cart» перекрыла бы корзину — ловим до сохранения."""
    for slug in ("cart", "admin", "search"):
        page = Page(title="Вредная", slug=slug)
        with pytest.raises(ValidationError):
            page.full_clean()


@pytest.mark.django_db
def test_page_url_does_not_shadow_catalog(client, db):
    """Маршрут cms стоит последним и не должен перехватывать разделы сайта."""
    category = Category.objects.create(name="Кремы", slug="kremy")
    Page.objects.create(title="Левая", slug="kremy-page")

    assert client.get("/cart/").status_code == 200
    assert client.get(category.get_absolute_url()).status_code == 200


@pytest.mark.django_db
def test_inactive_block_not_rendered(client, page):
    ContentBlock.objects.create(page=page, kind="text", content="Видимый", sort_order=10)
    ContentBlock.objects.create(
        page=page, kind="text", content="Скрытый", sort_order=20, is_active=False
    )
    html = client.get(page.get_absolute_url()).content.decode()
    assert "Видимый" in html
    assert "Скрытый" not in html


@pytest.mark.django_db
def test_blocks_respect_sort_order(client, page):
    ContentBlock.objects.create(page=page, kind="text", content="Второй", sort_order=20)
    ContentBlock.objects.create(page=page, kind="text", content="Первый", sort_order=10)
    html = client.get(page.get_absolute_url()).content.decode()
    assert html.index("Первый") < html.index("Второй")


@pytest.mark.django_db
def test_text_block_is_escaped(client, page):
    """Текстовый блок — это текст. Вставленный тег не должен исполниться."""
    ContentBlock.objects.create(page=page, kind="text", content="<script>alert(1)</script>")
    html = client.get(page.get_absolute_url()).content.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.django_db
def test_html_block_is_not_escaped(client, page):
    ContentBlock.objects.create(page=page, kind="html", content="<b>жирный</b>")
    html = client.get(page.get_absolute_url()).content.decode()
    assert "<b>жирный</b>" in html


@pytest.mark.django_db
def test_text_block_makes_paragraphs(client, page):
    ContentBlock.objects.create(page=page, kind="text", content="Первый.\n\nВторой.")
    html = client.get(page.get_absolute_url()).content.decode()
    assert html.count("<p>Первый.</p>") == 1
    assert "<p>Второй.</p>" in html


@pytest.mark.django_db
def test_block_validation_by_kind(page):
    with pytest.raises(ValidationError):
        ContentBlock(page=page, kind="cta", title="Купите").full_clean()
    with pytest.raises(ValidationError):
        ContentBlock(page=page, kind="image").full_clean()
    with pytest.raises(ValidationError):
        ContentBlock(page=page, kind="html").full_clean()


@pytest.mark.django_db
def test_products_block_shows_products(client, page):
    category = Category.objects.create(name="Кремы", slug="kremy")
    Product.objects.create(
        category=category,
        name="Крем дневной",
        slug="krem",
        sku="K-1",
        price=100,
        stock=5,
    )
    ContentBlock.objects.create(
        page=page, kind="products", title="Хиты", category=category, limit=4
    )
    html = client.get(page.get_absolute_url()).content.decode()
    assert "Крем дневной" in html


# ------------------------------------------------------------------ меню
@pytest.mark.django_db
def test_menu_item_requires_target(page):
    with pytest.raises(ValidationError):
        MenuItem(location="header", title="Пусто").full_clean()


@pytest.mark.django_db
def test_menu_item_rejects_two_targets(page):
    category = Category.objects.create(name="Кремы", slug="kremy")
    item = MenuItem(location="header", title="Двойной", page=page, category=category)
    with pytest.raises(ValidationError):
        item.full_clean()


@pytest.mark.django_db
def test_menu_item_url_resolution(page):
    item = MenuItem.objects.create(location="header", title="О нас", page=page)
    assert item.get_url() == page.get_absolute_url()

    manual = MenuItem.objects.create(location="footer", title="Корзина", url="/cart/")
    assert manual.get_url() == "/cart/"


@pytest.mark.django_db
def test_menu_rendered_in_header(client, page):
    MenuItem.objects.create(location="header", title="О компании", page=page)
    html = client.get(reverse("catalog:home")).content.decode()
    assert "О компании" in html
    assert page.get_absolute_url() in html


@pytest.mark.django_db
def test_inactive_menu_item_hidden(client, page):
    MenuItem.objects.create(location="header", title="Скрытый пункт", page=page, is_active=False)
    html = client.get(reverse("catalog:home")).content.decode()
    assert "Скрытый пункт" not in html


# ------------------------------------------------------------- наполнение
@pytest.mark.django_db
def test_seed_cms_is_idempotent():
    from django.core.management import call_command

    call_command("seed_cms", verbosity=0)
    first = Page.objects.count()
    call_command("seed_cms", verbosity=0)

    assert Page.objects.count() == first
    assert MenuItem.objects.count() == 7


@pytest.mark.django_db
def test_seeded_pages_open(client):
    from django.core.management import call_command

    call_command("seed_cms", verbosity=0)
    for slug in ("about", "delivery", "contacts"):
        assert client.get(f"/{slug}/").status_code == 200
