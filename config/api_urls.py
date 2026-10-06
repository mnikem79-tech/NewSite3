"""Корень REST API. Приложения будут подключать сюда свои маршруты."""

from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView


class ApiRoot(APIView):
    """Заглушка корня API — пригодится для проверки работоспособности."""

    def get(self, request):
        return Response({"version": "v1", "endpoints": {}})


urlpatterns = [
    path("", ApiRoot.as_view(), name="api-root"),
]
