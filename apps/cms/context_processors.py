"""Настройки сайта и меню — нужны в шапке и подвале каждой страницы."""

from .models import MenuItem, SiteSettings


def site_settings(request):
    settings_obj = SiteSettings.load()
    menu = MenuItem.objects.active().select_related("page", "category")

    return {
        "site_settings": settings_obj,
        # site_name оставлен для совместимости с шаблонами этапов 8-9.
        "site_name": settings_obj.site_name,
        "header_menu": [item for item in menu if item.location == MenuItem.Location.HEADER],
        "footer_menu": [item for item in menu if item.location == MenuItem.Location.FOOTER],
    }
