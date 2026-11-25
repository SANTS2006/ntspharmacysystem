from django.urls import path

from . import views as v

urlpatterns = [
    path("shifts/", v.ShiftListView.as_view()),
    path("shifts/open/", v.OpenShiftView.as_view()),
    path("shifts/current/", v.CurrentShiftView.as_view()),
    path("shifts/<int:pk>/", v.ShiftDetailView.as_view()),
    path("shifts/<int:pk>/close/", v.CloseShiftView.as_view()),
    path("shifts/<int:pk>/cash-movements/", v.CashMovementView.as_view()),
    path("cash-movements/<int:pk>/approve/", v.DecideCashMovementView.as_view()),
    path("cash-movements/<int:pk>/reject/", v.RejectCashMovementView.as_view()),
    path("pos/products/", v.ProductSearchView.as_view()),
    path("pos/pending-dispensings/", v.PendingDispensingsView.as_view()),
    path("pos/dashboard/", v.CashierDashboardView.as_view()),
    path("sales/", v.SaleListCreateView.as_view()),
    path("sales/<int:pk>/", v.SaleDetailView.as_view()),
    path("sales/<int:pk>/payments/", v.AddPaymentView.as_view()),
    path("sales/<int:pk>/return/", v.ReturnView.as_view()),
    path("sales/<int:pk>/cancel/", v.CancelView.as_view()),
    path("sales/<int:pk>/receipt/", v.ReceiptView.as_view()),
    path("sales/<int:pk>/receipt/pdf/", v.ReceiptPdfView.as_view()),
    path("sales/<int:pk>/receipt/email/", v.ReceiptEmailView.as_view()),
]
