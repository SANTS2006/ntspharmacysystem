from django.urls import path

from . import views as v

urlpatterns = [
    path("suppliers/", v.SupplierListCreateView.as_view()),
    path("suppliers/<int:pk>/", v.SupplierDetailView.as_view()),
    path("procurement/requisitions/", v.RequisitionListCreateView.as_view()),
    path("procurement/requisitions/<int:pk>/submit/", v.RequisitionSubmit.as_view()),
    path("procurement/requisitions/<int:pk>/approve/", v.RequisitionApprove.as_view()),
    path("procurement/requisitions/<int:pk>/reject/", v.RequisitionReject.as_view()),
    path("procurement/requisitions/<int:pk>/cancel/", v.RequisitionCancel.as_view()),
    path("procurement/orders/", v.OrderListCreateView.as_view()),
    path("procurement/orders/<int:pk>/", v.OrderDetailView.as_view()),
    path("procurement/orders/<int:pk>/submit/", v.OrderSubmit.as_view()),
    path("procurement/orders/<int:pk>/approve/", v.OrderApprove.as_view()),
    path("procurement/orders/<int:pk>/reject/", v.OrderReject.as_view()),
    path("procurement/orders/<int:pk>/cancel/", v.OrderCancel.as_view()),
    path("procurement/goods-receipts/", v.GoodsReceiptView.as_view()),
    path("procurement/invoices/", v.InvoiceListCreateView.as_view()),
    path("procurement/invoices/<int:pk>/pay/", v.PayInvoiceView.as_view()),
    path("procurement/supplier-balances/", v.SupplierBalancesView.as_view()),
    path("procurement/returns/", v.PurchaseReturnView.as_view()),
]
