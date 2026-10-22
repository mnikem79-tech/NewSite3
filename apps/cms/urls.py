from django.urls import path

from . import views, views_admin

app_name = "cms"

urlpatterns = [
    # Адрес объявлен раньше страниц: правило ниже ловит любой слаг и
    # перехватило бы загрузку картинок. Доступ — только сотрудникам.
    path("cms/upload-image/", views_admin.upload_image, name="upload-image"),
    path("<slug:slug>/", views.PageDetailView.as_view(), name="page"),
]
