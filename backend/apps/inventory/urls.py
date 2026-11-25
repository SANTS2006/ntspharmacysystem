from django.urls import path

from . import views as v

urlpatterns = [
    path("batches/", v.BatchListView.as_view()),
    path("batches/<int:pk>/adjust/", v.AdjustView.as_view()),
    path("batches/<int:pk>/write-off/", v.WriteOffView.as_view()),
    path("batches/<int:pk>/status/", v.BatchStatusView.as_view()),
    path("inventory/overview/", v.OverviewView.as_view()),
    path("inventory/alerts/", v.AlertsView.as_view()),
    path("inventory/valuation/", v.ValuationView.as_view()),
    path("inventory/movements/", v.MovementListView.as_view()),
    path("inventory/receive/", v.ReceiveView.as_view()),
    path("inventory/recall/", v.RecallView.as_view()),
    path("inventory/transfers/", v.TransferView.as_view()),
]
