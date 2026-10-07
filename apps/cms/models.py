"""
Конструктор сайта: настройки, страницы из блоков, меню, медиатека.

Задача приложения — отдать владельцу магазина управление содержимым сайта,
не заставляя его править шаблоны. Всё, что здесь появляется, редактируется
в админке и не требует перезапуска сервера.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.models import ActivatableModel, SeoModel, SortableModel, TimeStampedModel
from apps.core.utils import prefix_path

# Адреса, занятые приложениями. Страница с таким slug перекрыла бы корзину
# или админку, причём заметили бы это не сразу.
RESERVED_SLUGS = {
    "admin",
    "api",
    "cart",
    "catalog",
    "checkout",
    "healthz",
    "media",
    "orders",
    "product",
    "search",
    "static",
}


def upload_to_pages(instance, filename):
    return f"pages/{filename}"


def upload_to_site(instance, filename):
    return f"site/{filename}"


def upload_to_library(instance, filename):
    return f"library/{filename}"


class SiteSettings(models.Model):
    """
    Настройки сайта в единственном экземпляре.

    Намеренно не кэшируется: при нескольких воркерах gunicorn локальный кэш
    у каждого свой, и правка в админке доходила бы до посетителей вразнобой.
    Один запрос по первичному ключу на страницу дешевле этой путаницы.
    """

    site_name = models.CharField(_("название сайта"), max_length=120, default="NewSite3")
    tagline = models.CharField(
        _("короткое описание"),
        max_length=200,
        blank=True,
        help_text=_("Выводится рядом с логотипом и в подвале."),
    )
    logo = models.ImageField(_("логотип"), upload_to=upload_to_site, blank=True)
    favicon = models.ImageField(_("иконка сайта"), upload_to=upload_to_site, blank=True)

    phone = models.CharField(_("телефон"), max_length=40, blank=True)
    email = models.EmailField(_("e-mail"), blank=True)
    address = models.CharField(_("адрес"), max_length=255, blank=True)
    work_hours = models.CharField(_("часы работы"), max_length=120, blank=True)

    vk_url = models.URLField(_("ВКонтакте"), blank=True)
    telegram_url = models.URLField(_("Telegram"), blank=True)
    whatsapp_url = models.URLField(_("WhatsApp"), blank=True)
    youtube_url = models.URLField(_("YouTube"), blank=True)

    footer_text = models.TextField(
        _("текст в подвале"),
        blank=True,
        help_text=_("Короткий абзац о компании. Переносы строк сохраняются."),
    )

    meta_description = models.CharField(
        _("описание сайта для поисковиков"),
        max_length=500,
        blank=True,
        help_text=_("Подставляется на страницах, где своё описание не задано."),
    )

    show_search = models.BooleanField(_("показывать поиск"), default=True)
    show_phone_in_header = models.BooleanField(_("телефон в шапке"), default=True)

    head_snippet = models.TextField(
        _("код в <head>"),
        blank=True,
        help_text=_("Счётчики и метрики. Вставляется как есть — только для администратора."),
    )
    body_snippet = models.TextField(
        _("код перед </body>"),
        blank=True,
        help_text=_("Чаты и виджеты. Вставляется как есть — только для администратора."),
    )

    updated_at = models.DateTimeField(_("изменено"), auto_now=True)

    class Meta:
        verbose_name = _("настройки сайта")
        verbose_name_plural = _("настройки сайта")

    def __str__(self):
        return str(_("Настройки сайта"))

    def save(self, *args, **kwargs):
        # Первичный ключ без default: Django сначала попробует UPDATE и только
        # при отсутствии строки сделает INSERT. С default=1 он всегда идёт в
        # INSERT и вторая попытка сохранения падает на уникальности ключа.
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(_("Настройки сайта удалить нельзя."))

    @classmethod
    def load(cls) -> "SiteSettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def socials(self):
        """Заполненные соцсети — чтобы шаблон не перебирал пустые поля."""
        pairs = (
            ("ВКонтакте", self.vk_url),
            ("Telegram", self.telegram_url),
            ("WhatsApp", self.whatsapp_url),
            ("YouTube", self.youtube_url),
        )
        return [{"title": title, "url": url} for title, url in pairs if url]


class PageQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_blocks(self):
        return self.prefetch_related("blocks__images", "blocks__category")


class Page(TimeStampedModel, ActivatableModel, SeoModel, SortableModel):
    """Произвольная страница, собранная из блоков."""

    class Layout(models.TextChoices):
        DEFAULT = "default", _("Обычная")
        WIDE = "wide", _("Во всю ширину")
        NARROW = "narrow", _("Узкая колонка (текст)")

    title = models.CharField(_("заголовок"), max_length=200)
    slug = models.SlugField(_("адрес"), max_length=200, unique=True)
    layout = models.CharField(
        _("вид страницы"), max_length=20, choices=Layout.choices, default=Layout.DEFAULT
    )
    intro = models.TextField(
        _("вступление"),
        blank=True,
        help_text=_("Короткий абзац под заголовком. Необязательно."),
    )
    show_title = models.BooleanField(
        _("показывать заголовок"),
        default=True,
        help_text=_("Снимите, если заголовок уже есть в первом блоке."),
    )

    is_system = models.BooleanField(
        _("системная"),
        default=False,
        editable=False,
        help_text=_("Такие страницы нельзя удалить: на них ссылается код."),
    )

    objects = PageQuerySet.as_manager()

    class Meta:
        verbose_name = _("страница")
        verbose_name_plural = _("страницы")
        ordering = ("sort_order", "title")

    def __str__(self):
        return self.title

    def clean(self):
        if not self.slug and self.title:
            self.slug = slugify(self.title, allow_unicode=False)
        if self.slug in RESERVED_SLUGS:
            raise ValidationError(
                {
                    "slug": _("Адрес «%(slug)s» занят разделом сайта. Выберите другой.")
                    % {"slug": self.slug}
                }
            )

    def get_absolute_url(self):
        return reverse("cms:page", kwargs={"slug": self.slug})

    @property
    def visible_blocks(self):
        return [block for block in self.blocks.all() if block.is_active]


class ContentBlock(ActivatableModel, SortableModel):
    """
    Блок содержимого. Один класс на все типы — потому что в админке блоки
    редактируются инлайном, а разнотипные инлайны Django показывать не умеет.
    Лишние поля для конкретного типа просто не используются; подсказки в
    админке объясняют, что заполнять.
    """

    class Kind(models.TextChoices):
        TEXT = "text", _("Текст")
        IMAGE = "image", _("Изображение")
        GALLERY = "gallery", _("Галерея")
        CTA = "cta", _("Призыв с кнопкой")
        PRODUCTS = "products", _("Подборка товаров")
        HTML = "html", _("Произвольный HTML")
        DIVIDER = "divider", _("Разделитель")

    page = models.ForeignKey(
        Page, verbose_name=_("страница"), on_delete=models.CASCADE, related_name="blocks"
    )
    kind = models.CharField(_("тип блока"), max_length=20, choices=Kind.choices, default=Kind.TEXT)

    title = models.CharField(_("заголовок блока"), max_length=200, blank=True)
    content = models.TextField(
        _("текст"),
        blank=True,
        help_text=_("Для типа «Текст» переносы строк превращаются в абзацы автоматически."),
    )

    image = models.ImageField(_("изображение"), upload_to=upload_to_pages, blank=True)
    image_alt = models.CharField(
        _("описание изображения"),
        max_length=200,
        blank=True,
        help_text=_("Текст для незрячих и на случай, если картинка не загрузится."),
    )

    link_url = models.CharField(
        _("ссылка"),
        max_length=500,
        blank=True,
        help_text=_("Можно относительную: /catalog/kremy/"),
    )
    link_text = models.CharField(_("текст кнопки"), max_length=100, blank=True)

    category = models.ForeignKey(
        "catalog.Category",
        verbose_name=_("категория"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Для подборки товаров. Пусто — избранные товары."),
    )
    limit = models.PositiveSmallIntegerField(
        _("сколько товаров"),
        default=4,
        help_text=_("Для подборки товаров."),
    )

    class Meta:
        verbose_name = _("блок")
        verbose_name_plural = _("блоки")
        ordering = ("sort_order", "pk")

    def __str__(self):
        label = self.title or self.get_kind_display()
        return f"{self.get_kind_display()}: {label}" if self.title else label

    def clean(self):
        """Проверяем то, без чего блок выведется пустым местом."""
        errors = {}
        if self.kind == self.Kind.TEXT and not self.content and not self.title:
            errors["content"] = _("Заполните текст или заголовок.")
        if self.kind == self.Kind.IMAGE and not self.image:
            errors["image"] = _("Для блока с изображением нужна картинка.")
        if self.kind == self.Kind.HTML and not self.content:
            errors["content"] = _("Вставьте HTML-код.")
        if self.kind == self.Kind.CTA and not self.link_url:
            errors["link_url"] = _("Кнопка без ссылки бесполезна.")
        if self.kind == self.Kind.CTA and not self.link_text:
            errors["link_text"] = _("Укажите надпись на кнопке.")
        if errors:
            raise ValidationError(errors)

    @property
    def template_name(self):
        return f"cms/blocks/{self.kind}.html"

    @property
    def link_href(self) -> str:
        """Ссылка блока с учётом подкаталога домена."""
        return prefix_path(self.link_url)

    def get_products(self):
        """Товары для подборки. Импорт внутри — чтобы не связывать модели жёстко."""
        from apps.catalog.models import Product

        queryset = Product.objects.active().select_related("category").prefetch_related("images")
        if self.category_id:
            queryset = queryset.filter(category=self.category)
        else:
            queryset = queryset.filter(is_featured=True)
        return queryset[: self.limit or 4]


class BlockImage(SortableModel):
    """Картинка галереи. Отдельной моделью — галерей с одной картинкой не бывает."""

    block = models.ForeignKey(
        ContentBlock, verbose_name=_("блок"), on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(_("изображение"), upload_to=upload_to_pages)
    alt = models.CharField(_("описание"), max_length=200, blank=True)
    caption = models.CharField(_("подпись"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("изображение галереи")
        verbose_name_plural = _("изображения галереи")
        ordering = ("sort_order", "pk")

    def __str__(self):
        return self.caption or self.alt or f"Изображение #{self.pk}"


class MenuItem(ActivatableModel, SortableModel):
    """
    Пункт меню. Цель задаётся одним из трёх способов: страница, категория
    или произвольный адрес — что заполнено, то и используется.
    """

    class Location(models.TextChoices):
        HEADER = "header", _("Шапка сайта")
        FOOTER = "footer", _("Подвал сайта")

    location = models.CharField(
        _("где показывать"),
        max_length=20,
        choices=Location.choices,
        default=Location.HEADER,
        db_index=True,
    )
    title = models.CharField(_("надпись"), max_length=100)

    page = models.ForeignKey(
        Page,
        verbose_name=_("страница сайта"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="menu_items",
    )
    category = models.ForeignKey(
        "catalog.Category",
        verbose_name=_("категория каталога"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="menu_items",
    )
    url = models.CharField(
        _("произвольный адрес"),
        max_length=500,
        blank=True,
        help_text=_("Например /cart/ или https://example.com"),
    )
    open_in_new_tab = models.BooleanField(_("открывать в новой вкладке"), default=False)

    class Meta:
        verbose_name = _("пункт меню")
        verbose_name_plural = _("меню сайта")
        ordering = ("location", "sort_order", "pk")

    def __str__(self):
        return f"{self.get_location_display()}: {self.title}"

    def clean(self):
        targets = [bool(self.page_id), bool(self.category_id), bool(self.url)]
        if not any(targets):
            raise ValidationError(_("Укажите, куда ведёт пункт: страница, категория или адрес."))
        if sum(targets) > 1:
            raise ValidationError(_("Выбрано несколько целей сразу. Оставьте что-то одно."))

    def get_url(self) -> str:
        if self.page_id:
            return self.page.get_absolute_url()
        if self.category_id:
            return self.category.get_absolute_url()
        # Адрес вбит руками и про подкаталог домена не знает.
        return prefix_path(self.url)


class MediaFile(TimeStampedModel):
    """
    Медиатека: загруженные картинки с готовой ссылкой.

    Нужна для блоков с произвольным HTML и для писем — вставить картинку
    в код можно, только если у неё уже есть постоянный адрес.
    """

    title = models.CharField(_("название"), max_length=200, blank=True)
    image = models.ImageField(_("файл"), upload_to=upload_to_library)
    alt = models.CharField(_("описание"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("файл медиатеки")
        verbose_name_plural = _("медиатека")
        ordering = ("-created_at",)

    def __str__(self):
        return self.title or self.image.name
