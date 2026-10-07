from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Payment, PaymentMethod


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("provider", "is_active")
    search_fields = ("title", "code")
    prepopulated_fields = {"code": ("title",)}

    fieldsets = (
        (None, {"fields": ("title", "code", "description", "provider")}),
        (_("После оформления"), {"fields": ("instructions",)}),
        (
            _("Настройки провайдера"),
            {
                "classes": ("collapse",),
                "fields": ("config",),
                "description": _("Ключи API в формате JSON. Для оплаты при получении не нужны."),
            },
        ),
        (_("Отображение"), {"fields": ("sort_order", "is_active")}),
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "order_link", "method", "amount", "status_badge", "paid_at")
    list_filter = ("status", "method", "created_at")
    search_fields = ("order__number", "external_id")
    readonly_fields = (
        "order",
        "method",
        "amount",
        "currency",
        "external_id",
        "payload",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    @admin.display(description=_("Заказ"))
    def order_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.number)

    @admin.display(description=_("Статус"))
    def status_badge(self, obj):
        colors = {
            "pending": "#bf8700",
            "succeeded": "#137333",
            "failed": "#d93025",
            "refunded": "#6b7280",
        }
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors.get(obj.status, "#000"),
            obj.get_status_display(),
        )
