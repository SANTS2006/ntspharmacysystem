from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from django.conf import settings
from django.urls import re_path

from apps.backups import views as backup_views  # noqa: E402
from apps.core import seo
from apps.core.views import spa_index

urlpatterns = [
    path("health/live/", backup_views.live),
    path("health/ready/", backup_views.ready),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/platform/", include("apps.tenants.urls")),
    path("api/v1/platform/billing/", include("apps.billing.urls")),
    path("api/v1/public/", include("apps.tenants.public_urls")),
    path("api/v1/", include("apps.tenants.tenant_urls")),
    path("api/v1/", include("apps.medicines.urls")),
    path("api/v1/", include("apps.inventory.urls")),
    path("api/v1/", include("apps.procurement.urls")),
    path("api/v1/", include("apps.prescriptions.urls")),
    path("api/v1/", include("apps.sales.urls")),
    path("api/v1/", include("apps.shop.urls")),
    path("api/v1/", include("apps.payments.urls")),
    path("api/v1/", include("apps.accounting.urls")),
    path("api/v1/", include("apps.hr.urls")),
    path("api/v1/", include("apps.payroll.urls")),
    path("api/v1/", include("apps.engagement.urls")),
    path("api/v1/", include("apps.delivery.urls")),
    path("api/v1/", include("apps.reporting.urls")),
    path("api/v1/", include("apps.backups.urls")),
    path("api/v1/audit-logs/", include("apps.audit.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.billing.tenant_urls")),
    path("robots.txt", seo.robots_txt),
    path("sitemap.xml", seo.sitemap_xml),
    path("api/v1/", include("apps.website.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.ADMIN_ENABLED:
    urlpatterns.insert(2, path("admin/", admin.site.urls))

# Everything that is not API/health/admin/static is the React single-page app (client-side routing).
urlpatterns.append(re_path(r"^(?!api/|admin/|health/|ws/|static/).*$", spa_index))
