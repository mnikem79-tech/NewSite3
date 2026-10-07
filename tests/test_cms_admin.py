"""
Тесты админки конструктора.

Проверяется не вёрстка, а правила: кто что может менять и сохраняется ли
страница целиком вместе с блоками.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.cms.models import ContentBlock, Page, SiteSettings

User = get_user_model()


def page_form_data(page, blocks=(), initial=0):
    """Данные формы страницы вместе с инлайном блоков."""
    data = {
        "title": page.title,
        "slug": page.slug,
        "is_active": "on",
        "layout": page.layout,
        "show_title": "on",
        "intro": page.intro,
        "sort_order": page.sort_order,
        "meta_title": "",
        "meta_description": "",
        "blocks-TOTAL_FORMS": str(len(blocks)),
        "blocks-INITIAL_FORMS": str(initial),
        "blocks-MIN_NUM_FORMS": "0",
        "blocks-MAX_NUM_FORMS": "1000",
    }
    for index, block in enumerate(blocks):
        for key, value in block.items():
            data[f"blocks-{index}-{key}"] = value
    return data


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(email="root@example.com", password="pass123456")


@pytest.fixture
def editor(db):
    """Сотрудник с полными правами на CMS, но не администратор."""
    user = User.objects.create_user(
        email="editor@example.com", password="pass123456", is_staff=True
    )
    codenames = [
        f"{action}_{model}"
        for action in ("add", "change", "delete", "view")
        for model in ("page", "contentblock", "blockimage", "menuitem", "mediafile", "sitesettings")
    ]
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return user


@pytest.fixture
def page(db):
    return Page.objects.create(title="О компании", slug="about")


# ------------------------------------------------------------- страницы
@pytest.mark.django_db
def test_superuser_adds_block_through_admin(client, superuser, page):
    client.force_login(superuser)
    data = page_form_data(
        page,
        blocks=[
            {
                "kind": "text",
                "title": "Наша история",
                "content": "Работаем с 2019 года.",
                "sort_order": "10",
                "is_active": "on",
                "limit": "4",
                "id": "",
                "page": str(page.pk),
            }
        ],
    )
    response = client.post(reverse("admin:cms_page_change", args=[page.pk]), data, follow=True)
    assert response.status_code == 200
    assert page.blocks.count() == 1
    assert page.blocks.first().title == "Наша история"


@pytest.mark.django_db
def test_editor_cannot_create_raw_html_block(client, editor, page):
    """Произвольный HTML — только для администратора, и это не совет, а запрет."""
    client.force_login(editor)
    data = page_form_data(
        page,
        blocks=[
            {
                "kind": "html",
                "title": "",
                "content": "<script>alert(1)</script>",
                "sort_order": "10",
                "is_active": "on",
                "limit": "4",
                "id": "",
                "page": str(page.pk),
            }
        ],
    )
    client.post(reverse("admin:cms_page_change", args=[page.pk]), data)
    assert ContentBlock.objects.filter(kind="html").count() == 0


@pytest.mark.django_db
def test_editor_does_not_see_html_option(client, editor, page):
    client.force_login(editor)
    html = client.get(reverse("admin:cms_page_change", args=[page.pk])).content.decode()
    assert "Произвольный HTML" not in html


@pytest.mark.django_db
def test_superuser_sees_html_option(client, superuser, page):
    client.force_login(superuser)
    html = client.get(reverse("admin:cms_page_change", args=[page.pk])).content.decode()
    assert "Произвольный HTML" in html


@pytest.mark.django_db
def test_system_page_cannot_be_deleted(client, superuser):
    system = Page.objects.create(title="Контакты", slug="contacts", is_system=True)
    client.force_login(superuser)
    response = client.post(reverse("admin:cms_page_delete", args=[system.pk]), {"post": "yes"})
    assert response.status_code in (403, 302)
    assert Page.objects.filter(pk=system.pk).exists()


@pytest.mark.django_db
def test_regular_page_can_be_deleted(client, superuser, page):
    client.force_login(superuser)
    client.post(reverse("admin:cms_page_delete", args=[page.pk]), {"post": "yes"})
    assert not Page.objects.filter(pk=page.pk).exists()


# ------------------------------------------------------------- настройки
@pytest.mark.django_db
def test_settings_changelist_opens_the_only_record(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("admin:cms_sitesettings_changelist"))
    assert response.status_code == 302
    assert response["Location"].endswith("/1/change/")


@pytest.mark.django_db
def test_settings_add_page_is_closed(client, superuser):
    client.force_login(superuser)
    assert client.get(reverse("admin:cms_sitesettings_add")).status_code == 403


@pytest.mark.django_db
def test_editor_cannot_change_counters(client, editor):
    settings_obj = SiteSettings.load()
    client.force_login(editor)

    client.post(
        reverse("admin:cms_sitesettings_change", args=[settings_obj.pk]),
        {
            "site_name": "Магазин",
            "tagline": "",
            "phone": "",
            "email": "",
            "address": "",
            "work_hours": "",
            "vk_url": "",
            "telegram_url": "",
            "whatsapp_url": "",
            "youtube_url": "",
            "footer_text": "",
            "meta_description": "",
            "head_snippet": "<script>stealCookies()</script>",
            "body_snippet": "",
        },
    )
    settings_obj.refresh_from_db()
    assert settings_obj.head_snippet == ""


@pytest.mark.django_db
def test_superuser_can_change_counters(client, superuser):
    settings_obj = SiteSettings.load()
    client.force_login(superuser)

    client.post(
        reverse("admin:cms_sitesettings_change", args=[settings_obj.pk]),
        {
            "site_name": "Магазин",
            "tagline": "",
            "phone": "",
            "email": "",
            "address": "",
            "work_hours": "",
            "vk_url": "",
            "telegram_url": "",
            "whatsapp_url": "",
            "youtube_url": "",
            "footer_text": "",
            "meta_description": "",
            "head_snippet": "<!-- metrika -->",
            "body_snippet": "",
        },
    )
    settings_obj.refresh_from_db()
    assert settings_obj.head_snippet == "<!-- metrika -->"
    assert settings_obj.site_name == "Магазин"
