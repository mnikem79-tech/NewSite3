"""Данные, нужные на каждой странице витрины."""

from django.conf import settings


def site(request):
    from apps.catalog.models import Category

    return {
        "site_name": getattr(settings, "SITE_NAME", "NewSite3"),
        "menu_categories": Category.objects.active()
        .filter(parent__isnull=True)
        .order_by("sort_order", "name"),
        "search_query": request.GET.get("q", ""),
    }
