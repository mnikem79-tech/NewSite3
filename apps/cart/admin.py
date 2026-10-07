from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Корзины нужны в админке редко — в основном чтобы увидеть брошенные."""

    list_display = ("__str__", "count", "subtotal", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("user__email", "session_key")
    inlines = (CartItemInline,)
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        return (
            super().get_queryset(request).select_related("user").prefetch_related("items__product")
        )
