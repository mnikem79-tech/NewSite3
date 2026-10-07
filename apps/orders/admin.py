"""
Админка заказов — главный рабочий инструмент менеджера магазина.

Ключевой принцип: позиции оформленного заказа не редактируются. Это снимок
покупки, а не черновик. Менять суммы задним числом — прямой путь к спорам
с покупателем и расхождению с бухгалтерией.
"""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.payments.models import Payment

from .models import ALLOWED_TRANSITIONS, Order, OrderItem, OrderStatus, OrderStatusHistory
from .services import change_status

STATUS_COLORS = {
    OrderStatus.NEW: "#1f6feb",
    OrderStatus.CONFIRMED: "#0969da",
    OrderStatus.PACKED: "#8250df",
    OrderStatus.SHIPPED: "#bf8700",
    OrderStatus.DELIVERED: "#137333",
    OrderStatus.CANCELLED: "#6b7280",
    OrderStatus.REFUNDED: "#d93025",
}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product_link", "product_name", "product_sku", "price", "quantity", "total")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Карточка"))
    def product_link(self, obj):
        if not obj.product_id:
            return format_html('<span style="color:#999">товар удалён</span>')
        url = reverse("admin:catalog_product_change", args=[obj.product_id])
        return format_html('<a href="{}">открыть</a>', url)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("method", "amount", "currency", "status", "external_id", "paid_at")
    readonly_fields = ("method", "amount", "currency", "external_id")

    def has_add_permission(self, request, obj=None):
        return False


class StatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    fields = ("created_at", "from_status", "to_status", "user", "comment")
    readonly_fields = fields
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "created_short",
        "customer_name",
        "phone",
        "items_total",
        "total_display",
        "status_badge",
        "paid_badge",
    )
    list_display_links = ("number",)
    list_filter = ("status", "shipping_method", "payment_method", "created_at")
    search_fields = ("number", "customer_name", "email", "phone", "items__product_sku")
    date_hierarchy = "created_at"
    inlines = (OrderItemInline, PaymentInline, StatusHistoryInline)
    list_per_page = 50
    save_on_top = True

    readonly_fields = (
        "number",
        "created_at",
        "updated_at",
        "subtotal",
        "total",
        "shipping_method_title",
        "payment_method_title",
        "user",
    )

    fieldsets = (
        (None, {"fields": ("number", "status", ("created_at", "updated_at"))}),
        (_("Покупатель"), {"fields": ("user", "customer_name", "email", "phone")}),
        (
            _("Доставка"),
            {
                "fields": (
                    "shipping_method",
                    "shipping_method_title",
                    "shipping_address",
                    "shipping_cost",
                )
            },
        ),
        (_("Оплата"), {"fields": ("payment_method", "payment_method_title")}),
        (_("Суммы"), {"fields": ("subtotal", "discount", "total", "currency")}),
        (_("Комментарии"), {"fields": ("comment", "manager_note")}),
    )

    actions = ("action_confirm", "action_pack", "action_ship", "action_cancel")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("shipping_method", "payment_method", "user")
            .annotate(_items=Count("items", distinct=True), _qty=Sum("items__quantity"))
        )

    # ------------------------------------------------------------ колонки
    @admin.display(description=_("Создан"), ordering="created_at")
    def created_short(self, obj):
        return obj.created_at.strftime("%d.%m.%Y %H:%M")

    @admin.display(description=_("Позиций"), ordering="_items")
    def items_total(self, obj):
        return f"{obj._items} ({obj._qty or 0} шт.)"

    @admin.display(description=_("Итого"), ordering="total")
    def total_display(self, obj):
        return format_html("<b>{} ₽</b>", f"{obj.total:.0f}")

    @admin.display(description=_("Статус"), ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;white-space:nowrap">{}</span>',
            STATUS_COLORS.get(obj.status, "#6b7280"),
            obj.get_status_display(),
        )

    @admin.display(description=_("Оплата"), boolean=True)
    def paid_badge(self, obj):
        return obj.is_paid

    # ------------------------------------------------------------ сохранение
    def save_model(self, request, obj, form, change):
        """Смена статуса из формы идёт через сервис: проверка перехода,
        история и возврат остатков происходят всегда, а не иногда."""
        if not change:
            super().save_model(request, obj, form, change)
            return

        previous = Order.objects.get(pk=obj.pk).status
        new_status = obj.status

        if previous != new_status:
            obj.status = previous  # откатываем, сервис выставит сам
            super().save_model(request, obj, form, change)
            try:
                change_status(obj, new_status, user=request.user, comment="Изменён в админке")
                messages.success(
                    request, f"Статус заказа {obj.number} изменён на «{obj.get_status_display()}»."
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        else:
            super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.recalculate()

    # ------------------------------------------------------------ действия
    def _bulk_change(self, request, queryset, new_status):
        done, failed = 0, 0
        for order in queryset:
            try:
                change_status(order, new_status, user=request.user, comment="Массовое действие")
                done += 1
            except ValidationError:
                failed += 1
        if done:
            messages.success(request, f"Изменено заказов: {done}")
        if failed:
            messages.warning(
                request,
                f"Пропущено: {failed} — переход из текущего статуса не разрешён.",
            )

    @admin.action(description=_("Подтвердить заказы"))
    def action_confirm(self, request, queryset):
        self._bulk_change(request, queryset, OrderStatus.CONFIRMED)

    @admin.action(description=_("Отметить собранными"))
    def action_pack(self, request, queryset):
        self._bulk_change(request, queryset, OrderStatus.PACKED)

    @admin.action(description=_("Отметить отправленными"))
    def action_ship(self, request, queryset):
        self._bulk_change(request, queryset, OrderStatus.SHIPPED)

    @admin.action(description=_("Отменить заказы (вернуть остатки)"))
    def action_cancel(self, request, queryset):
        self._bulk_change(request, queryset, OrderStatus.CANCELLED)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        """В выпадающем списке статусов показываем только допустимые переходы."""
        if db_field.name == "status":
            order_id = request.resolver_match.kwargs.get("object_id")
            if order_id:
                order = Order.objects.filter(pk=order_id).first()
                if order:
                    allowed = {order.status, *ALLOWED_TRANSITIONS.get(order.status, ())}
                    kwargs["choices"] = [
                        (value, label) for value, label in OrderStatus.choices if value in allowed
                    ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "order", "from_status", "to_status", "user", "comment")
    list_filter = ("to_status", "created_at")
    search_fields = ("order__number",)
    readonly_fields = ("order", "from_status", "to_status", "user", "comment", "created_at")

    def has_add_permission(self, request):
        return False
