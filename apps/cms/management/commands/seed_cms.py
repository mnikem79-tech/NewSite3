"""
Начальное содержимое сайта.

Свежеустановленный магазин не должен выглядеть пустым: покупателю нужны
страницы о доставке, оплате и контактах, а владельцу — готовые образцы,
которые проще отредактировать, чем создать с нуля.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cms.models import ContentBlock, MenuItem, Page, SiteSettings

PAGES = [
    {
        "slug": "about",
        "title": "О компании",
        "intro": "Коротко о том, кто мы и почему нам можно доверять.",
        "sort_order": 10,
        "is_system": True,
        "blocks": [
            {
                "kind": "text",
                "title": "Чем мы занимаемся",
                "content": (
                    "Мы продаём товары, которым доверяем сами. "
                    "Каждую позицию проверяем перед отправкой.\n\n"
                    "Этот текст — образец. Откройте «Конструктор сайта → Страницы → "
                    "О компании» и замените его своим."
                ),
            },
            {
                "kind": "cta",
                "title": "Остались вопросы?",
                "content": "Напишите или позвоните — поможем подобрать товар.",
                "link_text": "Связаться с нами",
                "link_url": "/contacts/",
                "sort_order": 20,
            },
        ],
    },
    {
        "slug": "delivery",
        "title": "Доставка и оплата",
        "intro": "Как получить заказ и чем за него заплатить.",
        "sort_order": 20,
        "is_system": True,
        "blocks": [
            {
                "kind": "text",
                "title": "Способы доставки",
                "content": (
                    "Самовывоз — бесплатно, со склада в рабочее время.\n\n"
                    "Курьер по городу — 350 рублей, бесплатно при заказе от 5000 рублей. "
                    "Доставляем за один-два дня.\n\n"
                    "Почта и транспортные компании — по весу заказа, "
                    "250 рублей плюс 80 рублей за килограмм.\n\n"
                    "Условия настраиваются в разделе «Способы доставки»."
                ),
            },
            {
                "kind": "text",
                "title": "Способы оплаты",
                "content": (
                    "Оплата при получении — наличными или картой.\n\n"
                    "Счёт для организаций — безналичный расчёт, "
                    "счёт приходит на почту в течение рабочего дня."
                ),
                "sort_order": 20,
            },
        ],
    },
    {
        "slug": "contacts",
        "title": "Контакты",
        "intro": "",
        "sort_order": 30,
        "is_system": True,
        "blocks": [
            {
                "kind": "text",
                "title": "Как с нами связаться",
                "content": (
                    "Телефон, адрес и часы работы заполняются один раз в разделе "
                    "«Конструктор сайта → Настройки сайта» и выводятся в подвале "
                    "на каждой странице."
                ),
            },
        ],
    },
]

MENU = {
    "header": [
        {"title": "О компании", "page": "about", "sort_order": 10},
        {"title": "Доставка и оплата", "page": "delivery", "sort_order": 20},
        {"title": "Контакты", "page": "contacts", "sort_order": 30},
    ],
    "footer": [
        {"title": "О компании", "page": "about", "sort_order": 10},
        {"title": "Доставка и оплата", "page": "delivery", "sort_order": 20},
        {"title": "Контакты", "page": "contacts", "sort_order": 30},
        {"title": "Корзина", "url": "/cart/", "sort_order": 40},
    ],
}


class Command(BaseCommand):
    help = "Создаёт настройки сайта, стартовые страницы и меню"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Перезаписать содержимое стартовых страниц, если они уже есть",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options["force"]

        settings_obj = SiteSettings.load()
        if not settings_obj.phone:
            settings_obj.tagline = settings_obj.tagline or "интернет-магазин"
            settings_obj.phone = "+7 900 000-00-00"
            settings_obj.email = "shop@example.com"
            settings_obj.address = "г. Москва, ул. Примерная, 1"
            settings_obj.work_hours = "Пн–Пт 9:00–18:00"
            settings_obj.footer_text = (
                "Интернет-магазин на NewSite3. " "Замените этот текст в настройках сайта."
            )
            settings_obj.save()
            self.stdout.write("  + настройки сайта заполнены образцом")

        created_pages = 0
        for data in PAGES:
            blocks = data.pop("blocks")
            page, is_new = Page.objects.get_or_create(slug=data["slug"], defaults=data)

            if is_new:
                created_pages += 1
                self.stdout.write(f"  + страница: {page.title}")
            elif force:
                page.blocks.all().delete()
                self.stdout.write(f"  ~ страница перезаписана: {page.title}")
            else:
                data["blocks"] = blocks
                continue

            for order, block in enumerate(blocks, start=1):
                block.setdefault("sort_order", order * 10)
                ContentBlock.objects.create(page=page, **block)

            data["blocks"] = blocks

        created_menu = 0
        for location, items in MENU.items():
            for item in items:
                page_slug = item.get("page")
                defaults = {
                    "sort_order": item["sort_order"],
                    "url": item.get("url", ""),
                }
                if page_slug:
                    defaults["page"] = Page.objects.filter(slug=page_slug).first()

                _obj, is_new = MenuItem.objects.get_or_create(
                    location=location, title=item["title"], defaults=defaults
                )
                if is_new:
                    created_menu += 1

        if created_menu:
            self.stdout.write(f"  + пунктов меню: {created_menu}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Страниц: {Page.objects.count()} (новых: {created_pages}), "
                f"пунктов меню: {MenuItem.objects.count()}"
            )
        )
