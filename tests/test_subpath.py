"""
Работа сайта в подкаталоге домена (https://nail-app.ru/newsite3/).

Главный риск здесь — ссылка, потерявшая префикс: она уводит посетителя
в корень чужого домена, причём на странице выглядит обычной.
"""

import pytest
from django.test import override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from apps.catalog.models import Category
from apps.cms.models import ContentBlock, MenuItem, Page
from apps.core.utils import prefix_path

SUBPATH = {
    "SCRIPT_NAME": "/newsite3",
    "FORCE_SCRIPT_NAME": "/newsite3",
    "STATIC_URL": "/newsite3/static/",
    "MEDIA_URL": "/newsite3/media/",
}


@pytest.fixture
def subpath():
    """
    Префикс подкаталога для reverse().

    Одной настройки FORCE_SCRIPT_NAME мало: reverse() берёт префикс из
    потокового состояния, которое в обычной жизни выставляет обработчик
    запроса. В тестах его нужно задать руками и вернуть назад, иначе
    следующие тесты получат чужой префикс.
    """
    previous = get_script_prefix()
    set_script_prefix("/newsite3/")
    yield
    set_script_prefix(previous)


# --------------------------------------------------------- адреса страниц
@pytest.mark.django_db
@override_settings(**SUBPATH)
def test_reverse_includes_prefix(subpath):
    assert reverse("cart:detail") == "/newsite3/cart/"
    assert reverse("orders:checkout") == "/newsite3/checkout/"
    assert reverse("catalog:home") == "/newsite3/"


@pytest.mark.django_db
@override_settings(**SUBPATH)
def test_model_urls_include_prefix(subpath):
    category = Category.objects.create(name="Кремы", slug="kremy")
    page = Page.objects.create(title="О компании", slug="about")

    assert category.get_absolute_url() == "/newsite3/catalog/kremy/"
    assert page.get_absolute_url() == "/newsite3/about/"


def test_reverse_without_prefix_unchanged():
    assert reverse("cart:detail") == "/cart/"


# ------------------------------------------------------- ручные ссылки
@override_settings(**SUBPATH)
def test_prefix_path_adds_prefix():
    assert prefix_path("/cart/") == "/newsite3/cart/"
    assert prefix_path("/") == "/newsite3/"


@override_settings(**SUBPATH)
def test_prefix_path_leaves_external_links_alone():
    """Чужие адреса, якоря и почта префикса получить не должны."""
    for url in (
        "https://example.com/page",
        "//cdn.example.com/x.png",
        "mailto:shop@example.com",
        "tel:+79000000000",
        "#section",
        "",
    ):
        assert prefix_path(url) == url


@override_settings(**SUBPATH)
def test_prefix_path_is_idempotent():
    """Повторное применение не должно давать /newsite3/newsite3/."""
    once = prefix_path("/cart/")
    assert prefix_path(once) == once


@pytest.mark.django_db
@override_settings(**SUBPATH)
def test_menu_item_manual_url_gets_prefix():
    item = MenuItem.objects.create(location="footer", title="Корзина", url="/cart/")
    assert item.get_url() == "/newsite3/cart/"


@pytest.mark.django_db
@override_settings(**SUBPATH)
def test_menu_item_external_url_untouched():
    item = MenuItem.objects.create(location="footer", title="Партнёр", url="https://example.com")
    assert item.get_url() == "https://example.com"


@pytest.mark.django_db
@override_settings(**SUBPATH)
def test_block_link_gets_prefix():
    page = Page.objects.create(title="О компании", slug="about")
    block = ContentBlock.objects.create(
        page=page, kind="cta", title="Звоните", link_url="/contacts/", link_text="Связаться"
    )
    assert block.link_href == "/newsite3/contacts/"


# ------------------------------------------------------------- страницы
@pytest.mark.django_db
@override_settings(**SUBPATH)
def test_rendered_page_has_no_bare_links(client, subpath):
    """
    На отрисованной странице не должно остаться внутренних ссылок без префикса:
    такая ссылка увела бы покупателя на основной сайт в корне домена.
    """
    import re

    Page.objects.create(title="О компании", slug="about")
    MenuItem.objects.create(location="footer", title="Корзина", url="/cart/")

    html = client.get("/", SCRIPT_NAME="/newsite3").content.decode()

    bare = {
        href for href in re.findall(r'href="(/[^"]*)"', html) if not href.startswith("/newsite3")
    }
    assert not bare, f"ссылки без префикса: {sorted(bare)}"


@pytest.mark.django_db
@override_settings(**SUBPATH)
def test_static_and_media_urls_have_prefix(client, subpath):
    html = client.get("/", SCRIPT_NAME="/newsite3").content.decode()
    assert "/newsite3/static/css/site.css" in html
    assert "/newsite3/static/css/theme.css" in html


# --------------------------------------------- картинки, загруженные в админке
@pytest.fixture
def reload_urls():
    """
    Перечитать корневые маршруты.

    Набор маршрутов собирается один раз при импорте config.urls, поэтому
    простого override_settings мало: ветка SERVE_MEDIA уже отработала.
    Фикстура перечитывает модуль и обязательно возвращает всё назад —
    иначе следующие тесты получат чужой urlconf.
    """
    import importlib

    from django.urls import clear_url_caches

    import config.urls

    def _reload():
        importlib.reload(config.urls)
        clear_url_caches()

    yield _reload
    _reload()


@pytest.mark.django_db
def test_media_is_served_when_enabled(client, tmp_path, reload_urls):
    """
    На боевом хосте Caddy живёт в контейнере и до каталога media не достаёт,
    поэтому картинки отдаёт сам Django. Whitenoise для этого не годится:
    он составляет список файлов при старте и свежую загрузку из админки
    показал бы только после перезапуска службы.
    """
    (tmp_path / "banner.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    with override_settings(DEBUG=False, SERVE_MEDIA=True, MEDIA_ROOT=tmp_path, **SUBPATH):
        reload_urls()
        response = client.get("/media/banner.png", SCRIPT_NAME="/newsite3")

    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"\x89PNG")


@pytest.mark.django_db
def test_media_is_not_served_when_disabled(client, tmp_path, reload_urls):
    """По умолчанию раздачей занимается фронт-сервер — Django молчит."""
    (tmp_path / "banner.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    with override_settings(DEBUG=False, SERVE_MEDIA=False, MEDIA_ROOT=tmp_path, **SUBPATH):
        reload_urls()
        response = client.get("/media/banner.png", SCRIPT_NAME="/newsite3")

    assert response.status_code == 404
