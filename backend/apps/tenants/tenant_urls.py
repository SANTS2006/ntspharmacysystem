from django.urls import path

from apps.accounts import staff_views as s
from . import branch_views as b, pharmacy_views as p

urlpatterns = [
    path("branches/", b.BranchListCreateView.as_view(), name="branch-list"),
    path("branches/<int:pk>/", b.BranchDetailView.as_view(), name="branch-detail"),
    path("staff/", s.StaffListCreateView.as_view(), name="staff-list"),
    path("staff/<int:pk>/", s.StaffDetailView.as_view(), name="staff-detail"),
    path("roles/", s.RoleListView.as_view(), name="role-list"),
    path("roles/<int:pk>/", s.RoleDetailView.as_view(), name="role-detail"),
    path("tenants/me/", p.PharmacySettingsView.as_view(), name="pharmacy-settings"),
    path("tenants/dashboard/", p.TenantDashboardView.as_view(), name="tenant-dashboard"),
]
