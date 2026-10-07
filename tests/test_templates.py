"""
Проверки самих шаблонов, а не отрисованных ими страниц.

Поводом послужила настоящая ошибка: комментарий `{# … #}`, разбитый на две
строки, Django комментарием не считает и печатает как обычный текст. На
странице магазина появилась служебная фраза «Переопределяет только палитру
и детали…», и заметил её живой человек, а не тесты.
"""

from pathlib import Path

import pytest
from django.template.loader import render_to_string
from django.test import override_settings

from apps.cms.models import MenuItem, Page

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = sorted(BASE_DIR.glob("templates/**/*.html")) + sorted(
    BASE_DIR.glob("apps/**/templates/**/*.html")
)


def test_templates_are_found():
    """Если шаблоны перестанут находиться, остальные проверки станут пустыми."""
    assert len(TEMPLATES) > 10


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: str(p.relative_to(BASE_DIR)))
def test_comment_tags_close_on_same_line(path):
    """
    `{#` и `#}` обязаны стоять в одной строке.

    Django разбирает такой комментарий построчно: перенос превращает его в
    видимый текст на странице.
    """
    offenders = [
        (number, line.rstrip())
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.count("{#") != line.count("#}")
    ]

    assert not offenders, f"комментарий разорван переносом строки: {offenders}"


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: str(p.relative_to(BASE_DIR)))
def test_block_tags_are_balanced(path):
    """Парные теги должны закрываться — незакрытый `{% block %}` ломает страницу."""
    text = path.read_text(encoding="utf-8")

    for tag in ("block", "if", "for", "comment", "with", "spaceless"):
        opened = text.count("{% " + tag + " ") + text.count("{%" + tag + " ")
        closed = text.count("{% end" + tag + " %}") + text.count("{% end" + tag + "%}")
        if tag == "block":
            # {% block x %}…{% endblock x %} — закрытие может нести имя.
            closed = text.count("{% endblock")
        assert opened == closed, f"{tag}: открыто {opened}, закрыто {closed}"


@pytest.mark.django_db
def test_rendered_page_has_no_template_syntax():
    """Ни одна служебная конструкция не должна доезжать до посетителя."""
    page = Page.objects.create(title="О компании", slug="about")
    MenuItem.objects.create(location="header", title="О компании", page=page)

    html = render_to_string("cms/page.html", {"page": page, "site_settings": None})

    for marker in ("{#", "#}", "{%", "%}", "{{", "}}"):
        assert marker not in html, f"в выдаче осталось {marker}"


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_storefront_home_has_no_template_syntax(client):
    html = client.get("/").content.decode()

    for marker in ("{#", "#}", "{%", "{{"):
        assert marker not in html, f"на главной осталось {marker}"
