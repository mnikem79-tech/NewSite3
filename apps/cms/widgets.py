"""Визуальный редактор содержимого для админки.

Используется Jodit: лицензия MIT, ни одной внешней зависимости, работает
без сборщика — один файл скрипта и один файл стилей. Это важно, потому
что проект принципиально собирается без npm и без обращений к чужим
серверам: все файлы лежат в static/vendor/jodit.

Редактор открывается сразу в двух половинах: сверху — текст как он будет
выглядеть, снизу — его HTML. Правка в любой половине отражается в другой.
"""

import json

from django import forms
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# Панель инструментов. Порядок осмысленный: сначала то, чем пользуются
# постоянно, в конце — служебное. Названия кнопок — из самого Jodit.
TOOLBAR = [
    "undo",
    "redo",
    "|",
    "paragraph",
    "font",
    "fontsize",
    "brush",
    "|",
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "|",
    "align",
    "ul",
    "ol",
    "outdent",
    "indent",
    "|",
    "image",
    "ns3Columns",  # своя кнопка: разбить на колонки
    "table",
    "link",
    "hr",
    "|",
    "eraser",
    "copyformat",
    "|",
    "source",
    "preview",
    "fullsize",
]


class RichTextWidget(forms.Textarea):
    """Поле с визуальным редактором вместо обычной «простыни» текста."""

    class Media:
        css = {"all": ("vendor/jodit/jodit.min.css", "cms/admin-editor.css")}
        js = (
            "vendor/jodit/jodit.min.js",
            "vendor/jodit/jodit.ru.js",
            "cms/admin-editor.js",
        )

    def __init__(self, attrs=None, height: int = 520):
        self.height = height
        super().__init__(attrs)

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        css = attrs.get("class", "")
        attrs["class"] = f"{css} ns3-rich".strip()
        # Настройки читает admin-editor.js: так они не дублируются в JS
        # и остаются на виду рядом с панелью инструментов.
        attrs["data-jodit"] = json.dumps(
            {
                "language": "ru",
                "height": self.height,
                "defaultMode": 3,  # 3 = текст и HTML одновременно
                "toolbarButtonSize": "middle",
                "buttons": TOOLBAR,
                "buttonsMD": TOOLBAR,
                "buttonsSM": TOOLBAR,
                "buttonsXS": ["bold", "italic", "|", "ul", "ol", "|", "source"],
                "uploader": {
                    "url": reverse("cms:upload-image"),
                    "format": "json",
                    "method": "POST",
                    "pathVariableName": "path",
                },
                "showCharsCounter": True,
                "showWordsCounter": True,
                "showXPathInStatusbar": False,
                "askBeforePasteHTML": False,
                "askBeforePasteFromWord": False,
                "defaultActionOnPaste": "insert_clear_html",
                "placeholder": str(_("Текст блока…")),
            },
            ensure_ascii=False,
            default=str,
        )
        return attrs
