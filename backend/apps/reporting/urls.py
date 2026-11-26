from django.urls import path

from . import views as v

urlpatterns = [
    path("analytics/", v.AnalyticsView.as_view()),
    path("analytics/platform/", v.PlatformAnalyticsView.as_view()),
    path("reports/", v.ReportListView.as_view()),
    path("reports/dashboard/", v.DashboardView.as_view()),
    path("reports/<slug:slug>/", v.ReportView.as_view()),
]
