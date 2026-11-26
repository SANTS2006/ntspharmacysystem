"""Staff "Customers" module: everyone who registered on this pharmacy's website, with their profile and history."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import LoginHistory, User
from apps.accounts.permissions import HasTenantPermission
from apps.audit import services as audit
from apps.core.views import TenantContextMixin
from apps.engagement.models import Appointment, CustomerInquiry, Feedback
from apps.inventory.selectors import branch_ids_for

from .models import CustomerProfile, Order

PAID = ["payment_confirmed", "processing", "preparing", "ready_for_pickup", "out_for_delivery", "delivered", "completed"]


class Base(TenantContextMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "customer.view", "PATCH": "customer.manage"}

    def customers(self):
        return User.objects.filter(tenant=self.request.user.tenant, role__code="customer")

    def orders(self):
        """Branch-scoped staff only ever see the order history of their own branch."""
        ids = branch_ids_for(self.request.user)
        return Order.objects.filter(branch_id__in=ids) if ids else Order.objects.all()


def summary_row(u: User, profile, stats) -> dict:
    s = stats.get(u.pk, {})
    return {"id": u.pk, "full_name": u.full_name, "email": u.email, "phone": u.phone, "avatar": u.avatar.url if u.avatar else None,
            "email_verified": u.email_verified, "is_active": u.is_active, "joined": u.date_joined,
            "address": profile.address if profile else "", "gender": profile.gender if profile else "",
            "orders": s.get("orders", 0), "spent": s.get("spent") or Decimal("0.00"), "last_order": s.get("last")}


def order_stats(orders, ids):
    rows = orders.filter(customer_id__in=ids).values("customer_id").annotate(orders=Count("id"), spent=Sum("total", filter=Q(status__in=PAID)), last=Max("created_at"))
    return {r["customer_id"]: r for r in rows}


class CustomerListView(Base):
    ORDERING = {"name": "full_name", "-name": "-full_name", "joined": "date_joined", "-joined": "-date_joined"}

    def get(self, request):
        qs = self.customers()
        everyone = qs
        if term := request.query_params.get("search", "").strip():
            qs = qs.filter(Q(full_name__icontains=term) | Q(email__icontains=term) | Q(phone__icontains=term))
        flag = request.query_params.get("status")
        if flag == "verified":
            qs = qs.filter(email_verified=True, is_active=True)
        elif flag == "unverified":
            qs = qs.filter(email_verified=False)
        elif flag == "inactive":
            qs = qs.filter(is_active=False)
        qs = qs.order_by(self.ORDERING.get(request.query_params.get("ordering", ""), "-date_joined"), "-pk")
        pg = PageNumberPagination()
        pg.page_size = 12
        page = pg.paginate_queryset(qs, request)
        ids = [u.pk for u in page]
        profiles = {p.user_id: p for p in CustomerProfile.objects.filter(user_id__in=ids)}
        stats = order_stats(self.orders(), ids)
        resp = pg.get_paginated_response([summary_row(u, profiles.get(u.pk), stats) for u in page])
        resp.data["summary"] = {"total": everyone.count(), "verified": everyone.filter(email_verified=True).count(),
                                "new_30_days": everyone.filter(date_joined__gte=timezone.now() - timedelta(days=30)).count(),
                                "with_orders": self.orders().values("customer_id").distinct().count()}
        return resp


class ActiveIn(serializers.Serializer):
    is_active = serializers.BooleanField()


class CustomerDetailView(Base):
    def get(self, request, pk):
        u = get_object_or_404(self.customers(), pk=pk)
        profile = CustomerProfile.objects.filter(user=u).first()
        orders = self.orders().filter(customer=u).select_related("branch").order_by("-created_at")
        data = summary_row(u, profile, order_stats(self.orders(), [u.pk]))
        last_login = LoginHistory.objects.filter(user=u, success=True).order_by("-pk").first()
        data.update({
            "last_login": getattr(last_login, "created_at", None),
            "date_of_birth": profile.date_of_birth if profile else None,
            "delivery_addresses": profile.delivery_addresses if profile else [],
            "emergency_contact_name": profile.emergency_contact_name if profile else "",
            "emergency_contact_phone": profile.emergency_contact_phone if profile else "",
            "notification_prefs": profile.notification_prefs if profile else {},
            "terms_version": profile.terms_version if profile else "",
            "terms_accepted_at": profile.terms_accepted_at if profile else None,
            "signed_up_with": "Google" if profile and profile.google_sub else "Email and password",
            "recent_orders": [{"id": o.pk, "reference_number": o.reference_number, "status": o.status, "total": o.total, "branch": o.branch.name,
                               "fulfilment": o.fulfilment, "payment_method": o.payment_method, "created_at": o.created_at} for o in orders[:100]],
            "appointments": [{"id": a.pk, "service": a.service.name, "status": a.status, "start_at": a.start_at}
                             for a in Appointment.objects.filter(customer=u).select_related("service").order_by("-start_at")[:50]],
            "inquiries": [{"id": i.pk, "kind": i.kind, "message": i.message, "status": i.status, "response": i.response, "created_at": i.created_at}
                          for i in CustomerInquiry.objects.filter(customer=u).order_by("-created_at")[:50]],
            "feedback": [{"id": f.pk, "rating": f.rating, "comment": f.comment, "response": f.response, "created_at": f.created_at}
                         for f in Feedback.objects.filter(customer=u).order_by("-created_at")[:50]],
        })
        return Response(data)

    def patch(self, request, pk):
        u = get_object_or_404(self.customers(), pk=pk)
        s = ActiveIn(data=request.data)
        s.is_valid(raise_exception=True)
        active = s.validated_data["is_active"]
        if u.is_active != active:
            u.is_active = active
            u.credential_version += 1  # signs the customer out everywhere
            u.save(update_fields=["is_active", "credential_version"])
            audit.record("customer.activated" if active else "customer.deactivated", actor=request.user, target=u, request=request)
        return self.get(request, pk)
