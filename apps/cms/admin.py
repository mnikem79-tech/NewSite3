"""
Админка конструктора.

Главная мысль: человек, который наполняет сайт, не обязан знать HTML.
Поэтому страница собирается из готовых блоков, а произвольный код доступен
только администратору — остальным он недоступен в принципе, а не «не
рекомендуется».
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import BlockImage, ContentBlock, MediaFile, MenuItem, Page, SiteSettings

RAW_HTML_WARNING = _(
    "Произвольный HTML может вставить на сайт что угодно, включая чужие скрипты. "
    "Поэтому он доступен только администратору."
)


def preview_tag(image, height=60):
    if not image:
        # mark_safe, а не format_html: подставлять нечего, а format_html
        # без аргументов в Django 6.0 убирают.
        return mark_safe('<span style="color:#999">—</span>')
    return format_html(
        '<img src="{}" style="height:{}px;border-radius:6px;'
        'border:1px solid #ddd;background:#fff" alt="">',
        image.url,
        height,
    )


# --------------------------------------------------------------- настройки
def social_field(label):
    """
    Адрес без схемы считаем https.

    Без явного assume_scheme Django 5.2 предупреждает о смене поведения
    в 6.0 при каждом построении формы. Задаём будущее поведение сразу.
    """
    return forms.URLField(label=label, required=False, assume_scheme="https")


class SiteSettingsForm(forms.ModelForm):
    vk_url = social_field(_("ВКонтакте"))
    telegram_url = social_field(_("Telegram"))
    whatsapp_url = social_field(_("WhatsApp"))
    youtube_url = social_field(_("YouTube"))

    class Meta:
        model = SiteSettings
        fields = (
            "site_name",
            "tagline",
            "logo",
            "favicon",
            "phone",
            "email",
            "address",
            "work_hours",
            "vk_url",
            "telegram_url",
            "whatsapp_url",
            "youtube_url",
            "footer_text",
            "meta_description",
            "show_search",
            "show_phone_in_header",
            "head_snippet",
            "body_snippet",
        )

    def clean(self):
        data = super().clean()
        if not getattr(self, "_is_superuser", False):
            for field in ("head_snippet", "body_snippet"):
                if data.get(field) != getattr(self.instance, field, ""):
                    raise ValidationError({field: RAW_HTML_WARNING})
        return data


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Запись одна: список сразу открывает её на редактирование."""

    form = SiteSettingsForm
    save_on_top = True
    readonly_fields = ("logo_preview", "favicon_preview", "updated_at")

    fieldsets = (
        (
            _("Общее"),
            {
                "fields": (
                    "site_name",
                    "tagline",
                    ("logo", "logo_preview"),
                    ("favicon", "favicon_preview"),
                )
            },
        ),
        (_("Контакты"), {"fields": ("phone", "email", "address", "work_hours")}),
        (
            _("Социальные сети"),
            {"fields": ("vk_url", "telegram_url", "whatsapp_url", "youtube_url")},
        ),
        (_("Подвал"), {"fields": ("footer_text",)}),
        (_("Шапка"), {"fields": ("show_search", "show_phone_in_header")}),
        (
            _("Поисковые системы"),
            {"classes": ("collapse",), "fields": ("meta_description",)},
        ),
        (
            _("Счётчики и виджеты"),
            {
                "classes": ("collapse",),
                "fields": ("head_snippet", "body_snippet"),
                "description": RAW_HTML_WARNING,
            },
        ),
        (None, {"fields": ("updated_at",)}),
    )

    @admin.display(description=_("Как выглядит"))
    def logo_preview(self, obj):
        return preview_tag(obj.logo, 50)

    @admin.display(description=_("Как выглядит"))
    def favicon_preview(self, obj):
        return preview_tag(obj.favicon, 32)

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)
        is_superuser = request.user.is_superuser

        class Bound(form_class):
            def __init__(self, *args, **inner):
                super().__init__(*args, **inner)
                self._is_superuser = is_superuser
                if not is_superuser:
                    for name in ("head_snippet", "body_snippet"):
                        if name in self.fields:
                            self.fields[name].disabled = True
                            self.fields[name].help_text = RAW_HTML_WARNING

        return Bound

    def changelist_view(self, request, extra_context=None):
        obj = SiteSettings.load()
        return HttpResponseRedirect(reverse("admin:cms_sitesettings_change", args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ------------------------------------------------------------------ блоки
class ContentBlockForm(forms.ModelForm):
    class Meta:
        model = ContentBlock
        fields = (
            "page",
            "kind",
            "sort_order",
            "is_active",
            "title",
            "content",
            "image",
            "image_alt",
            "link_text",
            "link_url",
            "category",
            "limit",
        )
        widgets = {
            "content": forms.Textarea(attrs={"rows": 6, "style": "width:100%;max-width:60em"}),
        }

    def clean(self):
        data = super().clean()
        if data.get("kind") == ContentBlock.Kind.HTML and not getattr(self, "_is_superuser", True):
            raise ValidationError({"kind": RAW_HTML_WARNING})
        return data


class ContentBlockInline(admin.StackedInline):
    model = ContentBlock
    form = ContentBlockForm
    extra = 0
    ordering = ("sort_order", "pk")
    autocomplete_fields = ("category",)
    readonly_fields = ("gallery_link", "image_preview")

    fieldsets = (
        (None, {"fields": (("kind", "sort_order", "is_active"), "title")}),
        (
            _("Содержимое"),
            {
                "fields": (
                    "content",
                    ("image", "image_preview"),
                    "image_alt",
                    ("link_text", "link_url"),
                    ("category", "limit"),
                    "gallery_link",
                ),
                "description": _(
                    "Заполняйте то, что нужно выбранному типу: "
                    "«Текст» — текст; «Изображение» — картинка и описание; "
                    "«Призыв с кнопкой» — текст, надпись и ссылка; "
                    "«Подборка товаров» — категория и количество; "
                    "«Галерея» — сохраните блок и добавьте картинки по ссылке внизу."
                ),
            },
        ),
    )

    @admin.display(description=_("Как выглядит"))
    def image_preview(self, obj):
        return preview_tag(obj.image if obj and obj.pk else None)

    @admin.display(description=_("Картинки галереи"))
    def gallery_link(self, obj):
        if not obj or not obj.pk:
            return _("Сохраните страницу, чтобы добавить изображения.")
        if obj.kind != ContentBlock.Kind.GALLERY:
            return _("Только для типа «Галерея».")
        url = reverse("admin:cms_contentblock_change", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Добавить изображения ({})</a>',
            url,
            obj.images.count(),
        )

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        is_superuser = request.user.is_superuser
        base_form = formset.form

        class Bound(base_form):
            def __init__(self, *args, **inner):
                super().__init__(*args, **inner)
                self._is_superuser = is_superuser
                if not is_superuser and "kind" in self.fields:
                    self.fields["kind"].choices = [
                        (value, label)
                        for value, label in self.fields["kind"].choices
                        if value != ContentBlock.Kind.HTML
                    ]

        formset.form = Bound
        return formset


class BlockImageInline(admin.TabularInline):
    model = BlockImage
    extra = 3
    fields = ("image", "image_preview", "alt", "caption", "sort_order")
    readonly_fields = ("image_preview",)

    @admin.display(description=_("Как выглядит"))
    def image_preview(self, obj):
        return preview_tag(obj.image if obj and obj.pk else None)


@admin.register(ContentBlock)
class ContentBlockAdmin(admin.ModelAdmin):
    """Открывается по ссылке из страницы — ради картинок галереи."""

    form = ContentBlockForm
    inlines = (BlockImageInline,)
    list_display = ("__str__", "page", "kind", "sort_order", "is_active")
    list_filter = ("kind", "is_active")
    autocomplete_fields = ("category", "page")

    def get_model_perms(self, request):
        # Прячем из главного меню админки: блок редактируется в своей странице.
        return {}


# --------------------------------------------------------------- страницы
@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "blocks_count", "sort_order", "is_active", "view_link")
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active", "layout")
    search_fields = ("title", "slug", "blocks__content")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (ContentBlockInline,)
    save_on_top = True
    actions = ("action_publish", "action_unpublish")

    fieldsets = (
        (None, {"fields": ("title", "slug", "is_active")}),
        (_("Оформление"), {"fields": ("layout", "show_title", "intro", "sort_order")}),
        (
            _("Поисковые системы"),
            {"classes": ("collapse",), "fields": ("meta_title", "meta_description")},
        ),
    )

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(_blocks=Count("blocks"))

    @admin.display(description=_("Блоков"), ordering="_blocks")
    def blocks_count(self, obj):
        return obj._blocks

    @admin.display(description=_("На сайте"))
    def view_link(self, obj):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">открыть →</a>', obj.get_absolute_url()
        )

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        system = queryset.filter(is_system=True)
        if system.exists():
            messages.warning(
                request,
                _("Пропущены системные страницы: %(titles)s")
                % {"titles": ", ".join(system.values_list("title", flat=True))},
            )
        queryset.filter(is_system=False).delete()

    @admin.action(description=_("Опубликовать"))
    def action_publish(self, request, queryset):
        count = queryset.update(is_active=True)
        messages.success(request, _("Опубликовано страниц: %(n)s") % {"n": count})

    @admin.action(description=_("Снять с публикации"))
    def action_unpublish(self, request, queryset):
        count = queryset.update(is_active=False)
        messages.success(request, _("Скрыто страниц: %(n)s") % {"n": count})


# ------------------------------------------------------------------- меню
@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("title", "location", "target", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("location", "is_active")
    search_fields = ("title", "url")
    autocomplete_fields = ("page", "category")

    fieldsets = (
        (None, {"fields": ("location", "title", ("sort_order", "is_active"))}),
        (
            _("Куда ведёт"),
            {
                "fields": ("page", "category", "url", "open_in_new_tab"),
                "description": _("Заполните что-то одно: страницу, категорию или адрес."),
            },
        ),
    )

    @admin.display(description=_("Ведёт на"))
    def target(self, obj):
        return format_html("<code>{}</code>", obj.get_url())


# -------------------------------------------------------------- медиатека
@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = ("thumb", "title", "link", "created_at")
    list_display_links = ("thumb", "title")
    search_fields = ("title", "alt")
    readonly_fields = ("preview", "link", "created_at", "updated_at")
    fields = ("image", "preview", "title", "alt", "link", "created_at")

    @admin.display(description=_("Картинка"))
    def thumb(self, obj):
        return preview_tag(obj.image, 44)

    @admin.display(description=_("Просмотр"))
    def preview(self, obj):
        return preview_tag(obj.image, 220)

    @admin.display(description=_("Адрес для вставки"))
    def link(self, obj):
        if not obj.image:
            return "—"
        return format_html(
            '<input type="text" readonly value="{}" style="width:28em;font-family:monospace" '
            'onclick="this.select()">',
            obj.image.url,
        )
