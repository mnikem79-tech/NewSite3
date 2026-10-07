"""
Отправка писем по заказам.

Обёртка намеренно тонкая и «не падающая»: если SMTP недоступен, заказ всё
равно должен быть создан. Когда (и если) появится очередь задач, менять
придётся только это место, а не каждый вызов.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_order_confirmation(order) -> bool:
    """Письмо покупателю. Возвращает True, если отправлено."""
    context = {
        "order": order,
        "items": order.items.all(),
        "site_name": getattr(settings, "SITE_NAME", "NewSite3"),
    }
    try:
        subject = f"Заказ {order.number} принят"
        body = render_to_string("orders/email/confirmation.txt", context)
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            fail_silently=False,
        )
        logger.info("Письмо по заказу %s отправлено на %s", order.number, order.email)
        return True
    except Exception:
        logger.exception("Не удалось отправить письмо по заказу %s", order.number)
        return False


def send_status_change(order, previous_status: str) -> bool:
    context = {"order": order, "previous_status": previous_status}
    try:
        send_mail(
            subject=f"Заказ {order.number}: {order.get_status_display()}",
            message=render_to_string("orders/email/status.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Не удалось отправить уведомление по заказу %s", order.number)
        return False
