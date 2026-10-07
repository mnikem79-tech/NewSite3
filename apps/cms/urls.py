from django.urls import path

from . import views

app_name = "cms"

urlpatterns = [
    path("<slug:slug>/", views.PageDetailView.as_view(), name="page"),
]
