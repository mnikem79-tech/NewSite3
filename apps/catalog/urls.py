from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("search/", views.SearchView.as_view(), name="search"),
    path("catalog/<slug:slug>/", views.CategoryView.as_view(), name="category"),
    path("product/<slug:slug>/", views.ProductDetailView.as_view(), name="product"),
]
