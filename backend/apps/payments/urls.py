from django.urls import path

from . import views as v

urlpatterns = [
    path("webhooks/monime/", v.monime_webhook),
    path("webhooks/monime/<slug:slug>/", v.monime_webhook),  # older per-pharmacy address: same signature check
    path("shop/orders/<int:pk>/pay/", v.PayOrderView.as_view()),
    path("shop/orders/<int:pk>/payments/", v.OrderPaymentsView.as_view()),
    path("shop/orders/<int:pk>/payments/refresh/", v.RefreshOrderPaymentsView.as_view()),
    path("shop/orders/<int:pk>/receipt/", v.CustomerReceiptView.as_view()),
    path("shop/orders/<int:pk>/receipt/pdf/", v.CustomerReceiptPdfView.as_view()),
    path("shop/payments/", v.PaymentHistoryView.as_view()),
    path("payments/status/", v.StatusView.as_view()),
    path("payments/mobile-money/", v.CollectionsView.as_view()),
    path("payments/mobile-money/<int:pk>/", v.CollectionDetailView.as_view()),
    path("payments/mobile-money/<int:pk>/cancel/", v.CollectionCancelView.as_view()),
    path("payments/attempts/", v.AttemptsView.as_view()),
    path("payments/reconcile/", v.ReconcileView.as_view()),
    path("payments/reconciliation/", v.ReconciliationReportView.as_view()),
    path("orders/<int:pk>/receipt/", v.StaffReceiptView.as_view()),
    path("orders/<int:pk>/receipt/pdf/", v.StaffReceiptPdfView.as_view()),
    path("orders/<int:pk>/refund/", v.OrderRefundView.as_view()),
]
