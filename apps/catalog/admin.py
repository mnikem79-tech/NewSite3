"""Админка каталога: всё управление товарами происходит здесь."""

from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Attribute, Category, Product, ProductAttribute, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("indented_name", "products_count", "sort_order", "is_active")
    list_display_links = ("indented_name",)
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("parent",)

    fieldsets = (
        (None, {"fields": ("name", "slug", "parent", "description", "image")}),
        (_("Отображение"), {"fields": ("sort_order", "is_active")}),
        (
            _("SEO"),
            {
                "classes": ("collapse",),
                "fields": ("meta_title", "meta_description", "meta_keywords"),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("parent")
            .annotate(_products=Count("products"))
        )

    @admin.display(description=_("Категория"), ordering="name")
    def indented_name(self, obj):
        depth = len(obj.get_ancestors())
        return format_html("{}{}", "— " * depth, obj.name)

    @admin.display(description=_("Товаров"), ordering="_products")
    def products_count(self, obj):
        return obj._products


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("preview", "image", "alt", "is_main", "sort_order")
    readonly_fields = ("preview",)

    @admin.display(description=_("Превью"))
    def preview(self, obj):
        if obj.pk and obj.image:
            return format_html(
                '<img src="{}" style="max-height:60px;border-radius:4px">', obj.image.url
            )
        return "—"


class ProductAttributeInline(admin.TabularInline):
    model = ProductAttribute
    extra = 1
    autocomplete_fields = ("attribute",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "thumbnail",
        "name",
        "sku",
        "category",
        "price_display",
        "stock_display",
        "is_active",
        "is_featured",
    )
    list_display_links = ("thumbnail", "name")
    list_editable = ("is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "track_stock", "category")
    search_fields = ("name", "sku", "short_description")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category",)
    inlines = (ProductImageInline, ProductAttributeInline)
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50
    save_on_top = True
    actions = ("make_active", "make_inactive")

    fieldsets = (
        (None, {"fields": ("name", "slug", "sku", "category")}),
        (_("Описание"), {"fields": ("short_description", "description")}),
        (_("Цена"), {"fields": (("price", "old_price"),)}),
        (_("Склад"), {"fields": (("track_stock", "stock"), "weight")}),
        (_("Отображение"), {"fields": (("is_active", "is_featured"),)}),
        (
            _("SEO"),
            {
                "classes": ("collapse",),
                "fields": ("meta_title", "meta_description", "meta_keywords"),
            },
        ),
        (_("Служебное"), {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("category").prefetch_related("images")

    @admin.display(description="")
    def thumbnail(self, obj):
        image = obj.main_image
        if image:
            return format_html(
                '<img src="{}" style="height:40px;width:40px;object-fit:cover;border-radius:4px">',
                image.image.url,
            )
        return format_html('<span style="color:#bbb">нет фото</span>')

    @admin.display(description=_("Цена"), ordering="price")
    def price_display(self, obj):
        if obj.is_on_sale:
            return format_html(
                '<span style="color:#c00;font-weight:600">{}</span> '
                '<s style="color:#999">{}</s> <small>−{}%</small>',
                obj.price,
                obj.old_price,
                obj.discount_percent,
            )
        return obj.price

    @admin.display(description=_("Остаток"), ordering="stock")
    def stock_display(self, obj):
        if not obj.track_stock:
            return format_html('<span style="color:#888">без учёта</span>')
        if obj.stock == 0:
            return format_html('<span style="color:#c00;font-weight:600">нет</span>')
        if obj.stock < 5:
            return format_html('<span style="color:#e67e22">{}</span>', obj.stock)
        return obj.stock

    @admin.action(description=_("Включить выбранные товары"))
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, _("Включено товаров: %d") % updated)

    @admin.action(description=_("Отключить выбранные товары"))
    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, _("Отключено товаров: %d") % updated)


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "unit", "is_filterable", "sort_order", "values_count")
    list_editable = ("is_filterable", "sort_order")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_values=Count("values"))

    @admin.display(description=_("Используется у товаров"), ordering="_values")
    def values_count(self, obj):
        return obj._values
