"""Демо-наполнение: фотографии товаров и отсутствие выдуманных контактов."""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.management.commands.seed_demo import DEMO_IMAGES
from apps.catalog.models import Product, ProductImage
from apps.cms.models import SiteSettings


@pytest.fixture
def media(tmp_path, settings):
    """Снимки складываются во временную папку, а не в рабочую media/."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


def run(command: str, *args: str) -> str:
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


def test_demo_images_exist_in_repository():
    """Файлы лежат в репозитории: media/ в него не входит."""
    assert DEMO_IMAGES.is_dir(), f"нет папки {DEMO_IMAGES}"
    assert list(DEMO_IMAGES.glob("*.jpg")), "в репозитории нет демо-снимков"


@pytest.mark.django_db
def test_every_product_gets_a_photo(media):
    run("seed_demo")

    without = [p.sku for p in Product.objects.all() if not p.images.exists()]
    assert not without, f"товары без фотографии: {without}"

    main_images = ProductImage.objects.filter(is_main=True).count()
    assert main_images == Product.objects.count()


@pytest.mark.django_db
def test_second_run_does_not_duplicate_photos(media):
    run("seed_demo")
    first = ProductImage.objects.count()

    output = run("seed_demo")

    assert ProductImage.objects.count() == first
    assert "фотографий добавлено: 0" in output


@pytest.mark.django_db
def test_photos_can_be_skipped(media):
    run("seed_demo", "--no-images")
    assert ProductImage.objects.count() == 0


@pytest.mark.django_db
def test_seed_cms_does_not_invent_contacts():
    """Выдуманный телефон на живом сайте выглядит настоящим — его быть не должно."""
    run("seed_cms")

    site = SiteSettings.load()
    assert site.phone == ""
    assert site.email == ""
    assert site.address == ""
    assert site.show_phone_in_header is False


@pytest.mark.django_db
def test_contacts_command_sets_and_clears():
    call_command("site_contacts", "--phone", "+7 495 000-00-00", stdout=StringIO())
    site = SiteSettings.load()
    assert site.phone == "+7 495 000-00-00"
    assert site.show_phone_in_header is True

    call_command("site_contacts", "--clear", stdout=StringIO())
    site = SiteSettings.load()
    assert site.phone == ""
    assert site.show_phone_in_header is False
