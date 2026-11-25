from django.urls import path

from . import views as v

urlpatterns = [
    path("reports/", v.ReportListView.as_view()),
    path("reports/dashboard/", v.DashboardView.as_view()),
    path("reports/<slug:slug>/", v.ReportView.as_view()),
]
