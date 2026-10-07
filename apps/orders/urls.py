from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("orders/", views.OrderListView.as_view(), name="list"),
    path("orders/<str:number>/", views.OrderDetailView.as_view(), name="detail"),
    path("orders/<str:number>/success/", views.OrderSuccessView.as_view(), name="success"),
]
