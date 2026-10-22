"""Визуальный редактор: вывод содержимого, загрузка картинок, подключение."""

import json
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from PIL import Image

from apps.cms.admin import ContentBlockForm
from apps.cms.models import MediaFile
from apps.cms.templatetags.cms_content import rich_content


def make_image(name="photo.jpg", size=(60, 40), fmt="JPEG") -> BytesIO:
    buffer = BytesIO()
    Image.new("RGB", size, (200, 120, 150)).save(buffer, fmt)
    buffer.seek(0)
    buffer.name = name
    return buffer


# --- вывод содержимого на витрине ------------------------------------


class TestRichContent:
    def test_markup_from_editor_is_kept(self):
        html = "<p>Текст <strong>жирным</strong></p>"
        assert rich_content(html) == html

    def test_columns_survive(self):
        html = '<div class="cms-cols cms-cols-3"><div class="cms-col"></div></div>'
        assert "cms-cols-3" in rich_content(html)

    def test_plain_text_becomes_paragraphs(self):
        result = rich_content("Первый.\n\nВторой.")
        assert result == "<p>Первый.</p><p>Второй.</p>"

    def test_single_newline_is_a_line_break(self):
        assert rich_content("Строка\nещё строка") == "<p>Строка<br>ещё строка</p>"

    def test_plain_text_is_escaped(self):
        """Текст без разметки экранируется — иначе «<» ломал бы страницу."""
        assert rich_content("при t < 0 и a > b") == "<p>при t &lt; 0 и a &gt; b</p>"

    def test_empty_value(self):
        assert rich_content("") == ""
        assert rich_content(None) == ""


# --- подключение редактора в админке ---------------------------------


class TestWidget:
    def test_field_uses_editor(self):
        html = str(ContentBlockForm()["content"])
        assert "ns3-rich" in html
        assert "data-jodit" in html

    def test_settings_are_passed_to_browser(self):
        widget = ContentBlockForm().fields["content"].widget
        config = json.loads(widget.build_attrs({})["data-jodit"])

        assert config["language"] == "ru"
        assert config["defaultMode"] == 3, "текст и HTML должны быть видны сразу"
        assert "ns3Columns" in config["buttons"], "нет кнопки колонок"
        assert config["uploader"]["url"] == reverse("cms:upload-image")
        for button in ("fontsize", "image", "align", "bold", "italic", "source"):
            assert button in config["buttons"], f"нет кнопки {button}"

    def test_library_is_vendored_not_remote(self):
        """Файлы лежат у нас: проект не ходит на чужие серверы."""
        media = str(ContentBlockForm().media)
        assert "vendor/jodit/jodit.min.js" in media
        assert "vendor/jodit/jodit.ru.js" in media
        assert "//" not in media.replace("https://", "").replace("http://", "")


# --- загрузка картинок -----------------------------------------------


@pytest.fixture
def staff_client(client, db, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    user = get_user_model().objects.create_superuser(
        email="editor@example.com", password="EditorPass2026!"
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestUpload:
    url = "/cms/upload-image/"

    def test_image_goes_to_media_library(self, staff_client):
        response = staff_client.post(self.url, {"files[]": make_image()})

        body = response.json()
        assert body["success"] is True
        assert body["data"]["isImages"] == [True]
        assert MediaFile.objects.count() == 1, "файл не попал в медиатеку"
        assert body["data"]["files"][0] == MediaFile.objects.get().image.url

    def test_non_image_is_refused(self, staff_client):
        bad = BytesIO(b"#!/bin/sh\nrm -rf /")
        bad.name = "script.sh"

        body = staff_client.post(self.url, {"files[]": bad}).json()

        assert body["success"] is False
        assert MediaFile.objects.count() == 0

    def test_too_big_is_refused(self, staff_client, settings):
        from apps.cms import views_admin

        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 1024
        big = make_image(size=(400, 400))
        big.seek(0, 2)
        original, views_admin.MAX_SIZE = views_admin.MAX_SIZE, 10
        try:
            big.seek(0)
            body = staff_client.post(self.url, {"files[]": big}).json()
        finally:
            views_admin.MAX_SIZE = original

        assert body["success"] is False
        assert "12 МБ" in " ".join(body["data"]["messages"])

    def test_nothing_sent(self, staff_client):
        assert staff_client.post(self.url).json()["success"] is False

    def test_stranger_cannot_upload(self, client, db):
        response = client.post(self.url, {"files[]": make_image()})

        assert response.status_code in (302, 403), "посторонний смог загрузить файл"
        assert MediaFile.objects.count() == 0

    def test_get_is_not_allowed(self, staff_client):
        assert staff_client.get(self.url).status_code == 405
