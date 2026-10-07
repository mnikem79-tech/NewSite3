from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import ShippingMethod


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "calculation",
        "price",
        "free_from_amount",
        "requires_address",
        "sort_order",
        "is_active",
    )
    list_editable = ("sort_order", "is_active")
    list_filter = ("calculation", "is_active")
    search_fields = ("title", "code")
    prepopulated_fields = {"code": ("title",)}

    fieldsets = (
        (None, {"fields": ("title", "code", "description", "requires_address")}),
        (
            _("Расчёт стоимости"),
            {
                "fields": ("calculation", "price", "free_from_amount", "price_per_kg"),
                "description": _(
                    "Фиксированная — всегда «стоимость». "
                    "Бесплатно от суммы — нужна «бесплатно от суммы». "
                    "По весу — «стоимость» как база плюс «доплата за кг»."
                ),
            },
        ),
        (_("Отображение"), {"fields": ("sort_order", "is_active")}),
    )
