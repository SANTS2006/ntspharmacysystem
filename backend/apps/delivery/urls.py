from django.urls import path

from . import views as v

urlpatterns = [
    path("deliveries/", v.DeliveriesView.as_view()),
    path("deliveries/drivers/", v.DriversView.as_view()),
    path("deliveries/mine/", v.MyDeliveriesView.as_view()),
    path("deliveries/<int:pk>/pickup/", v.PickupView.as_view()),
    path("deliveries/<int:pk>/deliver/", v.DeliverView.as_view()),
    path("deliveries/<int:pk>/fail/", v.FailView.as_view()),
    path("shop/orders/<int:pk>/delivery/", v.CustomerDeliveryView.as_view()),
]
