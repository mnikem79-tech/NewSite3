"""
Публичная часть каталога.

Серверный рендеринг на шаблонах Django: один процесс, нечего собирать,
поисковые роботы получают готовый HTML. Для коробочного продукта это
минимум движущихся частей при установке.
"""

from django.db.models import Max, Min
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from .models import Attribute, Category, Product

PAGE_SIZE = 12

SORT_OPTIONS = {
    "new": ("-created_at", "Сначала новые"),
    "price": ("price", "Сначала дешёвые"),
    "-price": ("-price", "Сначала дорогие"),
    "name": ("name", "По названию"),
}
DEFAULT_SORT = "new"


class ProductFilterMixin:
    """Общая логика фильтрации и сортировки для списков товаров."""

    def get_sort_key(self) -> str:
        key = self.request.GET.get("sort", DEFAULT_SORT)
        return key if key in SORT_OPTIONS else DEFAULT_SORT

    def apply_filters(self, queryset):
        params = self.request.GET

        if params.get("in_stock"):
            queryset = queryset.available()

        # Цена: некорректный ввод молча игнорируем, страница не должна падать
        # из-за того, что кто-то подставил ?price_min=дешево в адресную строку.
        for param, lookup in (("price_min", "price__gte"), ("price_max", "price__lte")):
            raw = params.get(param)
            if raw:
                try:
                    queryset = queryset.filter(**{lookup: float(raw)})
                except (TypeError, ValueError):
                    pass

        # Фильтры по характеристикам: ?attr-material=металл
        # Несколько разных характеристик соединяются по И, поэтому для каждой
        # нужен отдельный filter() — иначе Django ищет одну строку связи,
        # удовлетворяющую всем условиям сразу, и результат всегда пустой.
        for key, value in params.items():
            if key.startswith("attr-") and value:
                slug = key[len("attr-") :]
                queryset = queryset.filter(
                    attributes__attribute__slug=slug, attributes__value=value
                )

        return queryset.distinct()

    def get_sorted(self, queryset):
        field, _label = SORT_OPTIONS[self.get_sort_key()]
        return queryset.order_by(field)

    def filter_context(self) -> dict:
        params = self.request.GET.copy()
        params.pop("page", None)
        return {
            "sort_options": SORT_OPTIONS,
            "current_sort": self.get_sort_key(),
            "querystring": params.urlencode(),
            "active_filters": {k: v for k, v in params.items() if k != "sort" and v},
        }


class HomeView(ListView):
    """Главная: рекомендуемые товары и корневые категории."""

    template_name = "catalog/home.html"
    context_object_name = "products"

    def get_queryset(self):
        return (
            Product.objects.active()
            .filter(is_featured=True)
            .select_related("category")
            .with_images()[:8]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = (
            Category.objects.active().filter(parent__isnull=True).order_by("sort_order", "name")
        )
        context["latest"] = (
            Product.objects.active()
            .select_related("category")
            .with_images()
            .order_by("-created_at")[:8]
        )
        return context


class CategoryView(ProductFilterMixin, ListView):
    """Список товаров категории со всеми вложенными подкатегориями."""

    template_name = "catalog/category.html"
    context_object_name = "products"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        self.category = get_object_or_404(Category.objects.active(), slug=self.kwargs["slug"])
        queryset = (
            Product.objects.active()
            .in_category(self.category)
            .select_related("category")
            .with_images()
        )
        return self.get_sorted(self.apply_filters(queryset))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category"] = self.category
        context["breadcrumbs"] = self.category.get_ancestors()
        context["children"] = self.category.children.filter(is_active=True).order_by(
            "sort_order", "name"
        )

        # Диапазон цен и доступные значения характеристик считаем по всей
        # категории, а не по отфильтрованной выборке — иначе фильтр
        # «схлопывается» после первого применения и его нельзя расширить.
        base = Product.objects.active().in_category(self.category)
        context["price_range"] = base.aggregate(min=Min("price"), max=Max("price"))
        context["facets"] = self.build_facets(base)
        context.update(self.filter_context())
        return context

    def build_facets(self, base_queryset) -> list[dict]:
        """Доступные значения фильтруемых характеристик в этой категории."""
        product_ids = base_queryset.values_list("pk", flat=True)
        facets = []
        for attribute in Attribute.objects.filter(is_filterable=True).order_by(
            "sort_order", "name"
        ):
            values = (
                attribute.values.filter(product_id__in=product_ids)
                .values_list("value", flat=True)
                .distinct()
                .order_by("value")
            )
            values = list(values)
            if values:
                facets.append(
                    {
                        "attribute": attribute,
                        "values": values,
                        "selected": self.request.GET.get(f"attr-{attribute.slug}", ""),
                    }
                )
        return facets


class ProductDetailView(DetailView):
    """Карточка товара."""

    template_name = "catalog/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return (
            Product.objects.active()
            .select_related("category")
            .prefetch_related("images", "attributes__attribute")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        context["breadcrumbs"] = [*product.category.get_ancestors(), product.category]
        context["images"] = list(product.images.all())
        context["related"] = (
            Product.objects.active()
            .filter(category=product.category)
            .exclude(pk=product.pk)
            .select_related("category")
            .with_images()[:4]
        )
        return context


class SearchView(ProductFilterMixin, ListView):
    """Поиск по каталогу с подстраховкой на опечатки через pg_trgm."""

    template_name = "catalog/search.html"
    context_object_name = "products"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        self.query = self.request.GET.get("q", "").strip()
        if not self.query:
            return Product.objects.none()

        base = Product.objects.active().select_related("category").with_images()
        queryset = base.search(self.query)

        self.fuzzy = False
        if not queryset.exists():
            fuzzy = self.similar_products(base)
            if fuzzy is not None:
                self.fuzzy = True
                return fuzzy

        return self.get_sorted(self.apply_filters(queryset))

    def similar_products(self, base):
        """Похожие названия — спасает от «наущники» вместо «наушники»."""
        try:
            from django.contrib.postgres.search import TrigramSimilarity
        except ImportError:  # pragma: no cover
            return None

        return (
            base.annotate(similarity=TrigramSimilarity("name", self.query))
            .filter(similarity__gt=0.2)
            .order_by("-similarity")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.query
        context["fuzzy"] = getattr(self, "fuzzy", False)
        context.update(self.filter_context())
        return context
