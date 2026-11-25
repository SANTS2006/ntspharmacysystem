from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import HasTenantPermission
from apps.core.views import TenantContextMixin
from apps.inventory.selectors import branch_ids_for
from apps.shop.models import Order
from apps.shop.views import IsVerifiedCustomer, staff_orders

from . import services
from .models import Delivery


class Base(TenantContextMixin):
    permission_classes = [HasTenantPermission]


def out(d: Delivery, driver_view=False):
    o = d.order
    x = {"id": d.pk, "order": o.pk, "reference": o.reference_number, "status": d.status, "driver": d.driver_id, "driver_name": d.driver.full_name, "note": d.note,
         "picked_up_at": d.picked_up_at, "finished_at": d.finished_at, "order_status": o.status}
    if driver_view:  # a driver sees only what is needed to deliver this order
        x.update(address=o.delivery_address, customer_name=o.customer.full_name, customer_phone=o.customer.phone, payment_method=o.payment_method, collect=str(o.total) if o.payment_method == "cash_on_delivery" else None)
    return x


class DeliveriesView(Base, APIView):
    required_permission = "delivery.manage"

    def get(self, request):
        qs = Delivery.objects.select_related("order", "driver")
        ids = branch_ids_for(request.user)
        if ids:
            qs = qs.filter(order__branch_id__in=ids)
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        pg = PageNumberPagination()
        return pg.get_paginated_response([out(d) for d in pg.paginate_queryset(qs, request)])

    def post(self, request):
        o = get_object_or_404(staff_orders(request.user), pk=request.data.get("order"))
        d = services.assign(o.pk, request.data.get("driver"), actor=request.user, note=str(request.data.get("note", "")))
        return Response(out(d), status=201)


class DriversView(Base, APIView):
    required_permission = "delivery.manage"

    def get(self, request):
        qs = User.objects.filter(tenant=request.user.tenant, is_active=True, role__code="delivery_personnel")
        ids = branch_ids_for(request.user)
        if ids:
            qs = qs.filter(branch_id__in=ids)
        return Response([{"id": u.pk, "name": u.full_name, "branch": u.branch_id, "phone": u.phone} for u in qs])


class MyDeliveriesView(Base, APIView):
    required_permission = "delivery.perform"

    def get(self, request):
        qs = Delivery.objects.filter(driver=request.user, status__in=["assigned", "picked_up"]).select_related("order__customer", "driver")
        return Response([out(d, True) for d in qs])


class DriverAction(Base, APIView):
    required_permission = "delivery.perform"
    what = "pickup"

    def post(self, request, pk):
        get_object_or_404(Delivery, pk=pk, driver=request.user)  # drivers can only touch their own deliveries
        if self.what == "pickup":
            d = services.pickup(pk, driver=request.user)
        elif self.what == "deliver":
            d = services.deliver(pk, driver=request.user, note=str(request.data.get("note", "")))
        else:
            d = services.fail(pk, driver=request.user, reason=str(request.data.get("reason", "")))
        return Response(out(Delivery.objects.select_related("order__customer", "driver").get(pk=d.pk), True))


class PickupView(DriverAction):
    what = "pickup"


class DeliverView(DriverAction):
    what = "deliver"


class FailView(DriverAction):
    what = "fail"


class CustomerDeliveryView(TenantContextMixin, APIView):
    permission_classes = [IsVerifiedCustomer]

    def get(self, request, pk):
        o = get_object_or_404(Order, pk=pk, customer=request.user)
        d = o.deliveries.exclude(status="cancelled").select_related("driver").first()
        return Response({"status": d.status, "driver_name": d.driver.full_name.split(" ")[0], "picked_up_at": d.picked_up_at, "finished_at": d.finished_at} if d else None)  # first name only
