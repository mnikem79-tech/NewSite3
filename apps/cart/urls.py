from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.CartView.as_view(), name="detail"),
    path("add/<int:product_id>/", views.add_to_cart, name="add"),
    path("update/<int:product_id>/", views.update_quantity, name="update"),
    path("remove/<int:product_id>/", views.remove_from_cart, name="remove"),
]
