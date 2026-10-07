"""
Каталог: категории, товары, изображения, характеристики.

Решения зафиксированы в docs/04-DATA-MODEL.md:
  - дерево категорий без django-mptt (обычный parent FK);
  - товар = одна продаваемая позиция, вариантов нет;
  - учёт остатка включается флагом track_stock у каждого товара.
"""

from decimal import Decimal

from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import (
    ActivatableModel,
    ActiveQuerySet,
    SeoModel,
    SortableModel,
    TimeStampedModel,
)

MAX_TREE_DEPTH = 5


class Category(TimeStampedModel, ActivatableModel, SortableModel, SeoModel):
    """Категория каталога. Дерево строится обычной ссылкой на родителя."""

    parent = models.ForeignKey(
        "self",
        verbose_name=_("родительская категория"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(_("название"), max_length=255)
    slug = models.SlugField(_("адрес (slug)"), max_length=255, unique=True)
    description = models.TextField(_("описание"), blank=True)
    image = models.ImageField(_("изображение"), upload_to="categories/", blank=True)

    class Meta:
        verbose_name = _("категория")
        verbose_name_plural = _("категории")
        ordering = ["sort_order", "name"]
        indexes = [models.Index(fields=["parent", "sort_order"])]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("catalog:category", kwargs={"slug": self.slug})

    def clean(self):
        super().clean()
        if self.parent_id and self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": _("Категория не может быть родителем самой себя.")})

        # Защита от циклов: A -> B -> A положит сайт при обходе дерева.
        ancestor = self.parent
        depth = 0
        while ancestor is not None:
            depth += 1
            if ancestor.pk == self.pk:
                raise ValidationError({"parent": _("Обнаружен цикл в дереве категорий.")})
            if depth > MAX_TREE_DEPTH:
                raise ValidationError(
                    {
                        "parent": _("Слишком глубокая вложенность категорий (максимум %d).")
                        % MAX_TREE_DEPTH
                    }
                )
            ancestor = ancestor.parent

    def get_ancestors(self) -> list["Category"]:
        """От корня к текущей категории — для хлебных крошек."""
        chain, node = [], self.parent
        while node is not None and len(chain) <= MAX_TREE_DEPTH:
            chain.append(node)
            node = node.parent
        return list(reversed(chain))

    def get_descendant_ids(self) -> list[int]:
        """ID категории и всех вложенных — для выборки товаров поддерева."""
        ids, queue = [self.pk], [self.pk]
        for _depth in range(MAX_TREE_DEPTH):
            if not queue:
                break
            queue = list(Category.objects.filter(parent_id__in=queue).values_list("pk", flat=True))
            ids.extend(queue)
        return ids

    @property
    def breadcrumb(self) -> str:
        return " / ".join([c.name for c in self.get_ancestors()] + [self.name])


class ProductQuerySet(ActiveQuerySet):
    def available(self):
        """Товары, которые реально можно купить прямо сейчас."""
        return self.active().filter(models.Q(track_stock=False) | models.Q(stock__gt=0))

    def in_category(self, category: Category):
        return self.filter(category_id__in=category.get_descendant_ids())

    def search(self, query: str):
        """Поиск по названию и артикулу. Опечатки ловит pg_trgm."""
        if not query:
            return self
        return self.filter(
            models.Q(name__icontains=query)
            | models.Q(sku__icontains=query)
            | models.Q(short_description__icontains=query)
        )

    def with_images(self):
        return self.prefetch_related("images")


class Product(TimeStampedModel, ActivatableModel, SeoModel):
    """Товар — единственная продаваемая единица (вариантов нет, см. решение в docs)."""

    category = models.ForeignKey(
        Category,
        verbose_name=_("категория"),
        on_delete=models.PROTECT,
        related_name="products",
    )
    name = models.CharField(_("название"), max_length=255, db_index=True)
    slug = models.SlugField(_("адрес (slug)"), max_length=255, unique=True)
    sku = models.CharField(_("артикул"), max_length=64, unique=True)

    short_description = models.CharField(
        _("краткое описание"),
        max_length=300,
        blank=True,
        help_text=_("Показывается в списке товаров."),
    )
    description = models.TextField(_("описание"), blank=True)

    price = models.DecimalField(
        _("цена"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    old_price = models.DecimalField(
        _("старая цена"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Зачёркнутая цена. Должна быть больше текущей."),
    )

    stock = models.PositiveIntegerField(_("остаток"), default=0)
    track_stock = models.BooleanField(
        _("вести учёт остатка"),
        default=True,
        help_text=_("Выключено — товар всегда доступен к заказу."),
    )

    weight = models.DecimalField(
        _("вес, кг"),
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_("Нужен для расчёта доставки по весу."),
    )
    is_featured = models.BooleanField(_("рекомендуемый"), default=False, db_index=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = _("товар")
        verbose_name_plural = _("товары")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "category"]),
            models.Index(fields=["is_featured", "is_active"]),
            # Триграммный индекс: ускоряет и LIKE '%...%', и поиск по
            # похожести. Без него оба варианта делают полный скан таблицы.
            GinIndex(
                fields=["name"],
                name="catalog_product_name_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="catalog_product_price_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(old_price__isnull=True)
                | models.Q(old_price__gt=models.F("price")),
                name="catalog_product_old_price_gt_price",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def get_absolute_url(self):
        return reverse("catalog:product", kwargs={"slug": self.slug})

    def clean(self):
        super().clean()
        if self.old_price is not None and self.price is not None and self.old_price <= self.price:
            raise ValidationError(
                {"old_price": _("Старая цена должна быть больше текущей, иначе скидки нет.")}
            )

    @property
    def in_stock(self) -> bool:
        return (not self.track_stock) or self.stock > 0

    @property
    def is_on_sale(self) -> bool:
        return self.old_price is not None and self.old_price > self.price

    @property
    def discount_percent(self) -> int:
        if not self.is_on_sale:
            return 0
        return int(round((self.old_price - self.price) / self.old_price * 100))

    @property
    def main_image(self):
        """Главное изображение, иначе первое по порядку, иначе None."""
        images = list(self.images.all())
        if not images:
            return None
        return next((i for i in images if i.is_main), images[0])


class ProductImage(SortableModel):
    """Изображение товара. Главное помечается флагом, а не полем в Product."""

    product = models.ForeignKey(
        Product,
        verbose_name=_("товар"),
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(_("изображение"), upload_to="products/%Y/%m/")
    alt = models.CharField(
        _("альт. текст"),
        max_length=255,
        blank=True,
        help_text=_("Пусто — подставится название товара."),
    )
    is_main = models.BooleanField(_("главное"), default=False)

    class Meta:
        verbose_name = _("изображение товара")
        verbose_name_plural = _("изображения товара")
        ordering = ["-is_main", "sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_main=True),
                name="catalog_one_main_image_per_product",
            )
        ]

    def __str__(self):
        return self.alt or f"Изображение {self.pk}"

    def save(self, *args, **kwargs):
        # Снимаем флаг с прежнего главного: ограничение в БД иначе не даст сохранить.
        if self.is_main:
            ProductImage.objects.filter(product=self.product, is_main=True).exclude(
                pk=self.pk
            ).update(is_main=False)
        super().save(*args, **kwargs)

    def get_alt(self) -> str:
        return self.alt or self.product.name


class Attribute(SortableModel):
    """Характеристика: «Материал», «Мощность», «Гарантия»."""

    name = models.CharField(_("название"), max_length=128, unique=True)
    slug = models.SlugField(_("код"), max_length=128, unique=True)
    unit = models.CharField(
        _("единица измерения"),
        max_length=32,
        blank=True,
        help_text=_("Например: кг, см, Вт. Можно оставить пустым."),
    )
    is_filterable = models.BooleanField(
        _("использовать в фильтрах"),
        default=False,
        help_text=_("Значения этой характеристики попадут в фильтр каталога."),
    )

    class Meta:
        verbose_name = _("характеристика")
        verbose_name_plural = _("характеристики")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name}, {self.unit}" if self.unit else self.name


class ProductAttribute(models.Model):
    """Значение характеристики у конкретного товара."""

    product = models.ForeignKey(
        Product,
        verbose_name=_("товар"),
        on_delete=models.CASCADE,
        related_name="attributes",
    )
    attribute = models.ForeignKey(
        Attribute,
        verbose_name=_("характеристика"),
        on_delete=models.PROTECT,
        related_name="values",
    )
    value = models.CharField(_("значение"), max_length=255)

    class Meta:
        verbose_name = _("значение характеристики")
        verbose_name_plural = _("характеристики товара")
        ordering = ["attribute__sort_order", "attribute__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "attribute"],
                name="catalog_unique_product_attribute",
            )
        ]

    def __str__(self):
        return f"{self.attribute.name}: {self.display_value}"

    @property
    def display_value(self) -> str:
        return f"{self.value} {self.attribute.unit}".strip()
