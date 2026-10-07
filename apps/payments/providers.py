"""
Абстракция платёжного провайдера.

Контракт намеренно узкий: создать платёж, обработать уведомление, вернуть
деньги. Приложение orders знает только этот интерфейс и ничего не знает
о конкретных API — поэтому подключение нового провайдера не трогает заказы.
"""

from __future__ import annotations

import logging

from django.utils.translation import gettext_lazy as _

from .models import Payment, PaymentMethod

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    """Провайдер не смог создать или подтвердить платёж."""


class BasePaymentProvider:
    """Базовый класс. Наследники реализуют работу с конкретным API."""

    code: str = ""

    def __init__(self, method: PaymentMethod):
        self.method = method
        self.config = method.config or {}

    def create_payment(self, order) -> Payment:
        """Создать запись о платеже. Возвращает Payment."""
        raise NotImplementedError

    def get_redirect_url(self, payment: Payment) -> str | None:
        """Куда отправить покупателя. None — редирект не нужен."""
        return None

    def handle_webhook(self, request) -> Payment | None:
        """Обработать уведомление от провайдера."""
        raise NotImplementedError

    def refund(self, payment: Payment, amount=None) -> Payment:
        raise NotImplementedError

    def get_instructions(self, payment: Payment) -> str:
        return self.method.instructions


class ManualProvider(BasePaymentProvider):
    """
    Оплата вне сайта: наличными при получении, переводом, по счёту.

    Платёж создаётся в статусе «ожидает» и переводится в «оплачен» вручную
    менеджером в админке. Это единственный провайдер в базовой поставке.
    """

    code = PaymentMethod.Provider.MANUAL

    def create_payment(self, order) -> Payment:
        payment = Payment.objects.create(
            order=order,
            method=self.method,
            amount=order.total,
            currency=order.currency,
            status=Payment.Status.PENDING,
        )
        logger.info("Создан платёж %s для заказа %s", payment.pk, order.number)
        return payment

    def handle_webhook(self, request):
        # Уведомлений нет: статус меняет менеджер.
        return None

    def refund(self, payment: Payment, amount=None) -> Payment:
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status", "updated_at"])
        return payment

    def get_instructions(self, payment: Payment) -> str:
        return self.method.instructions or str(
            _("Менеджер свяжется с вами для подтверждения заказа и оплаты.")
        )


PROVIDERS: dict[str, type[BasePaymentProvider]] = {
    ManualProvider.code: ManualProvider,
}


def get_provider(method: PaymentMethod) -> BasePaymentProvider:
    """Фабрика провайдеров. Неизвестный код — честная ошибка, а не тихий сбой."""
    provider_class = PROVIDERS.get(method.provider)
    if provider_class is None:
        raise PaymentError(f"Неизвестный провайдер оплаты: {method.provider}")
    return provider_class(method)


def register_provider(provider_class: type[BasePaymentProvider]) -> None:
    """Регистрация провайдера из стороннего модуля."""
    PROVIDERS[provider_class.code] = provider_class
