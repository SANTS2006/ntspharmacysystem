from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.PlanListCreateView.as_view()),
    path("invoices/", views.InvoiceListView.as_view()),
    path("invoices/issue/", views.IssueInvoiceView.as_view()),
    path("invoices/<int:pk>/pay/", views.PayView.as_view()),
    path("invoices/<int:pk>/refund/", views.RefundView.as_view()),
    path("invoices/<int:pk>/void/", views.VoidView.as_view()),
    path("revenue/", views.RevenueSummaryView.as_view()),
]
