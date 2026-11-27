from django.conf import settings
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound

from .models import Pharmacy


class PlatformInfoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"name": settings.PLATFORM_NAME, "whatsapp_number": settings.PLATFORM_WHATSAPP_NUMBER,
                         "contact_email": settings.PLATFORM_CONTACT_EMAIL,
                         "google_client_id": settings.GOOGLE_OAUTH_CLIENT_ID})  # a client id is public by design


def _online_payments(pharmacy) -> bool:
    from apps.payments.services import provider_ready
    return provider_ready(pharmacy)


class PharmacyBrandingView(APIView):
    """Public, unauthenticated: only non-sensitive branding/contact fields of ACTIVE pharmacies."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        p = Pharmacy.objects.filter(slug=slug, status=Pharmacy.Status.ACTIVE).first()
        if p is None:
            raise NotFound()
        return Response({
            "name": p.name, "slug": p.slug, "description": p.description,
            "logo": request.build_absolute_uri(p.logo.url) if p.logo else None,
            "primary_color": p.primary_color, "secondary_color": p.secondary_color,
            "contact_email": p.contact_email, "contact_phone": p.contact_phone,
            "address": p.address, "city": p.city, "country": p.country, "website_config": p.website_config,
            "online_payments": _online_payments(p)})


class PublicPlansView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from apps.billing.models import Plan
        return Response(list(Plan.objects.filter(is_active=True).order_by("price").values(
            "code", "name", "price", "currency", "interval", "max_branches", "max_users", "features")))


urlpatterns = [
    path("plans/", PublicPlansView.as_view()),
    path("platform/", PlatformInfoView.as_view()),
    path("pharmacies/<slug:slug>/", PharmacyBrandingView.as_view()),
]
