from django.urls import path

from . import tenant_views as v

urlpatterns = [
    path("subscription/", v.SubscriptionView.as_view()),
    path("subscription/invoices/<int:pk>/pay/", v.PayInvoiceView.as_view()),
    path("subscription/invoices/<int:pk>/refresh/", v.RefreshInvoiceView.as_view()),
]
