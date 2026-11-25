from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.PlatformDashboardView.as_view(), name="platform-dashboard"),
    path("pharmacies/<int:pk>/overview/", views.PharmacyDetailExtrasView.as_view(), name="pharmacy-overview"),
    path("pharmacies/", views.PharmacyListCreateView.as_view(), name="pharmacy-list"),
    path("pharmacies/<int:pk>/", views.PharmacyDetailView.as_view(), name="pharmacy-detail"),
    path("pharmacies/<int:pk>/suspend/", views.SuspendView.as_view(), name="pharmacy-suspend"),
    path("pharmacies/<int:pk>/activate/", views.ActivateView.as_view(), name="pharmacy-activate"),
]
