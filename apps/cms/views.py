"""Показ страниц, собранных в админке."""

from django.views.generic import DetailView

from .models import Page


class PageDetailView(DetailView):
    """
    Страница из блоков.

    Шаблон один: он перебирает блоки и подключает частичный шаблон по типу
    каждого. Добавление нового типа блока — это новый файл в cms/blocks/,
    без правок здесь.
    """

    model = Page
    context_object_name = "page"
    template_name = "cms/page.html"

    def get_queryset(self):
        queryset = Page.objects.with_blocks()
        # Черновик видит только персонал — чтобы было где подготовить страницу.
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.active()
        return queryset
