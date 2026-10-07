"""
Базовые способы доставки и оплаты.

После установки коробки они обязаны быть: без единого способа доставки
и оплаты оформить заказ физически невозможно, а покупатель дистрибутива
не обязан догадываться, что их надо создать руками.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.payments.models import PaymentMethod
from apps.shipping.models import ShippingMethod

SHIPPING = [
    {
        "code": "pickup",
        "title": "Самовывоз",
        "description": "Заберите заказ со склада в рабочее время.",
        "calculation": ShippingMethod.Calculation.FIXED,
        "price": Decimal("0.00"),
        "requires_address": False,
        "sort_order": 10,
    },
    {
        "code": "courier",
        "title": "Курьер по городу",
        "description": "Доставка в течение 1–2 дней.",
        "calculation": ShippingMethod.Calculation.FREE_FROM,
        "price": Decimal("350.00"),
        "free_from_amount": Decimal("5000.00"),
        "sort_order": 20,
    },
    {
        "code": "post",
        "title": "Почта / транспортная компания",
        "description": "Стоимость зависит от веса заказа.",
        "calculation": ShippingMethod.Calculation.BY_WEIGHT,
        "price": Decimal("250.00"),
        "price_per_kg": Decimal("80.00"),
        "sort_order": 30,
    },
]

PAYMENTS = [
    {
        "code": "on-delivery",
        "title": "Оплата при получении",
        "description": "Наличными или картой курьеру.",
        "instructions": "Оплатите заказ при получении — наличными или картой.",
        "provider": PaymentMethod.Provider.MANUAL,
        "sort_order": 10,
    },
    {
        "code": "invoice",
        "title": "Счёт для организаций",
        "description": "Безналичный расчёт по счёту.",
        "instructions": "Счёт на оплату придёт на указанный e-mail в течение рабочего дня.",
        "provider": PaymentMethod.Provider.MANUAL,
        "sort_order": 20,
    },
]


class Command(BaseCommand):
    help = "Создаёт базовые способы доставки и оплаты"

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for data in SHIPPING:
            _obj, is_new = ShippingMethod.objects.get_or_create(code=data["code"], defaults=data)
            if is_new:
                created += 1
                self.stdout.write(f"  + доставка: {data['title']}")

        for data in PAYMENTS:
            _obj, is_new = PaymentMethod.objects.get_or_create(code=data["code"], defaults=data)
            if is_new:
                created += 1
                self.stdout.write(f"  + оплата: {data['title']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Способов доставки: {ShippingMethod.objects.count()}, "
                f"оплаты: {PaymentMethod.objects.count()} (новых: {created})"
            )
        )
