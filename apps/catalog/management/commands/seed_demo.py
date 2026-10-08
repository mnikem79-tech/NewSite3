"""
Демо-наполнение каталога.

Нужно для дистрибутива: после установки коробки админка не должна быть пустой,
иначе непонятно, как ей пользоваться. Команда идемпотентна — повторный запуск
ничего не дублирует.

    python manage.py seed_demo
    python manage.py seed_demo --clear    # сначала удалить демо-данные
"""

from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import (
    Attribute,
    Category,
    Product,
    ProductAttribute,
    ProductImage,
)

# Снимки лежат в репозитории: папка media в него не входит, а витрина без
# фотографий выглядит незаконченной. Файл подбирается по артикулу товара.
DEMO_IMAGES = Path(__file__).resolve().parents[4] / "demo" / "products"

CATEGORIES = [
    ("Электроника", None, [("Смартфоны", None), ("Наушники", None)]),
    ("Дом и сад", None, [("Освещение", None), ("Посуда", None)]),
]

ATTRIBUTES = [
    ("Гарантия", "мес", True),
    ("Материал", "", True),
    ("Мощность", "Вт", False),
]

PRODUCTS = [
    # (категория, название, артикул, цена, старая цена, остаток, характеристики)
    (
        "Смартфоны",
        "Смартфон Aurora X5",
        "PHN-X5",
        "34990.00",
        "39990.00",
        12,
        {"Гарантия": "24", "Материал": "алюминий, стекло"},
    ),
    (
        "Смартфоны",
        "Смартфон Aurora Lite",
        "PHN-LT",
        "18490.00",
        None,
        3,
        {"Гарантия": "12", "Материал": "поликарбонат"},
    ),
    ("Наушники", "Наушники SoundWave Pro", "AUD-PRO", "7990.00", "9490.00", 0, {"Гарантия": "12"}),
    ("Наушники", "Наушники SoundWave Mini", "AUD-MIN", "2490.00", None, 45, {"Гарантия": "6"}),
    (
        "Освещение",
        "Лампа настольная Lumen",
        "LMP-01",
        "3250.00",
        None,
        8,
        {"Мощность": "12", "Материал": "металл"},
    ),
    (
        "Посуда",
        "Набор кастрюль Chef 5",
        "KTC-5",
        "12900.00",
        "15400.00",
        5,
        {"Материал": "нержавеющая сталь"},
    ),
]


def ru_slug(text: str) -> str:
    """slugify не умеет кириллицу — транслитерируем вручную."""
    table = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
    result = "".join(table.get(ch, table.get(ch.lower(), ch)) for ch in text.lower())
    return slugify(result)


class Command(BaseCommand):
    help = "Наполняет каталог демонстрационными данными"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Удалить демо-товары и категории перед наполнением",
        )
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="Не подключать фотографии из demo/products",
        )

    def attach_image(self, product) -> bool:
        """Ставит товару фотографию. Повторный запуск ничего не дублирует."""
        if product.images.exists():
            return False
        source = DEMO_IMAGES / f"{product.sku.lower()}.jpg"
        if not source.exists():
            return False
        image = ProductImage(product=product, alt=product.name, is_main=True)
        with source.open("rb") as fh:
            image.image.save(source.name, File(fh), save=False)
        image.save()
        return True

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            skus = [p[2] for p in PRODUCTS]
            deleted, _ = Product.objects.filter(sku__in=skus).delete()
            self.stdout.write(self.style.WARNING(f"Удалено объектов: {deleted}"))

        # --- характеристики ---
        attrs = {}
        for name, unit, filterable in ATTRIBUTES:
            attr, created = Attribute.objects.get_or_create(
                slug=ru_slug(name),
                defaults={"name": name, "unit": unit, "is_filterable": filterable},
            )
            attrs[name] = attr
            if created:
                self.stdout.write(f"  + характеристика: {name}")

        # --- категории ---
        cats = {}
        for order, (name, _parent, children) in enumerate(CATEGORIES, start=1):
            parent_obj, created = Category.objects.get_or_create(
                slug=ru_slug(name),
                defaults={"name": name, "sort_order": order * 10},
            )
            cats[name] = parent_obj
            if created:
                self.stdout.write(f"  + категория: {name}")

            for child_order, (child_name, _x) in enumerate(children, start=1):
                child, created = Category.objects.get_or_create(
                    slug=ru_slug(child_name),
                    defaults={
                        "name": child_name,
                        "parent": parent_obj,
                        "sort_order": child_order * 10,
                    },
                )
                cats[child_name] = child
                if created:
                    self.stdout.write(f"    + подкатегория: {child_name}")

        # --- товары ---
        created_count = 0
        images_count = 0
        for cat_name, name, sku, price, old_price, stock, spec in PRODUCTS:
            product, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "category": cats[cat_name],
                    "name": name,
                    "slug": ru_slug(name),
                    "short_description": f"{name} — демонстрационный товар.",
                    "description": (
                        f"Подробное описание товара «{name}». "
                        "Это демо-данные, созданные командой seed_demo. "
                        "Отредактируйте или удалите их в админке."
                    ),
                    "price": Decimal(price),
                    "old_price": Decimal(old_price) if old_price else None,
                    "stock": stock,
                    "is_featured": stock > 10,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  + товар: {name}")
                for attr_name, value in spec.items():
                    ProductAttribute.objects.create(
                        product=product, attribute=attrs[attr_name], value=value
                    )

            if not options["no_images"] and self.attach_image(product):
                images_count += 1
                self.stdout.write(f"    + фотография: {product.sku}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Категорий: {Category.objects.count()}, "
                f"товаров: {Product.objects.count()} (новых: {created_count}, "
                f"фотографий добавлено: {images_count})"
            )
        )
