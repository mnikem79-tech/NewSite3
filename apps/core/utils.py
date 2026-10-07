"""Мелкие помощники, нужные нескольким приложениям."""

from django.conf import settings


def prefix_path(url: str) -> str:
    """
    Добавляет префикс подкаталога к внутренней ссылке.

    Адреса, которые редактор вбил руками в админке («/cart/»), не проходят
    через reverse() и про подкаталог не знают. На https://домен/newsite3/
    такая ссылка увела бы посетителя на чужой сайт в корне домена.

    Внешние ссылки, якоря и mailto не трогаем.
    """
    prefix = getattr(settings, "SCRIPT_NAME", "") or ""
    if not prefix or not url:
        return url
    if not url.startswith("/") or url.startswith("//"):
        return url
    if url.startswith(prefix + "/") or url == prefix:
        return url
    return f"{prefix}{url}"
