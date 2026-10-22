"""Вывод содержимого блока на витрине.

Текстовые блоки раньше хранили обычный текст, и переносы строк
превращались в абзацы. С появлением визуального редактора в том же
поле лежит готовая разметка. Переключить вывод целиком нельзя: у
старых страниц абзацы бы слиплись в одну строку.

Поэтому решает само содержимое: есть разметка — выводим как есть,
нет — обходимся переносами строк, как раньше.
"""

import re

from django import template
from django.utils.safestring import mark_safe
from django.utils.text import normalize_newlines

register = template.Library()

# Теги, которые ставит редактор. Одиночная «<» в тексте (например,
# «при t < 0») разметкой не считается — нужен настоящий тег.
HTML_TAG = re.compile(
    r"<(/?)(p|div|br|h[1-6]|ul|ol|li|table|img|a|strong|em|b|i|u|s|span"
    r"|blockquote|pre|code|figure|hr|section)\b[^>]*>",
    re.IGNORECASE,
)


def looks_like_html(value: str) -> bool:
    return bool(HTML_TAG.search(value))


@register.filter(name="rich_content")
def rich_content(value) -> str:
    """Готовая разметка — как есть; простой текст — абзацами."""
    if not value:
        return ""

    text = str(value)
    if looks_like_html(text):
        return mark_safe(text)  # noqa: S308 - содержимое вводит сотрудник

    paragraphs = [p.strip() for p in normalize_newlines(text).split("\n\n") if p.strip()]
    rendered = "".join(
        "<p>{}</p>".format(p.replace("\n", "<br>")) for p in map(escape_text, paragraphs)
    )
    return mark_safe(rendered)  # noqa: S308 - текст экранирован построчно


def escape_text(value: str) -> str:
    from django.utils.html import escape

    return escape(value)
