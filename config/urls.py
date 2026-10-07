"""Корневые маршруты NewSite3."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve


def healthcheck(request):
    """Проверка живости для установщика, nginx и мониторинга."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthcheck, name="healthz"),
    path("api/v1/", include("config.api_urls")),
    path("cart/", include("apps.cart.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.catalog.urls")),
    # Последним: ловит /<slug>/ и перекрыл бы маршруты выше.
    path("", include("apps.cms.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    # MEDIA_URL содержит префикс подкаталога (/newsite3/media/), а до Django
    # запрос доходит уже без него — префикс живёт в SCRIPT_NAME. Маршрут
    # строим по остатку, иначе он никогда не совпадёт.
    _media_path = settings.MEDIA_URL.removeprefix(settings.SCRIPT_NAME).lstrip("/")
    urlpatterns += [
        re_path(
            rf"^{_media_path}(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]
