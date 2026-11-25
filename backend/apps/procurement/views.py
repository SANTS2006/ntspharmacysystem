from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission
from apps.audit import services as audit
from apps.core.fields import TenantPKField
from apps.core.views import TenantContextMixin
from apps.inventory.models import Batch
from apps.inventory.selectors import branch_ids_for
from apps.medicines.models import Medicine
from apps.tenants.models import Branch

from . import services
from .models import (GoodsReceipt, PurchaseOrder, PurchaseReturn, Requisition, Supplier, SupplierInvoice, SupplierPayment)


class Base(TenantContextMixin):
    permission_classes = [HasTenantPermission]


def own_branch_only(request, branch):
    if request.user.is_branch_scoped and branch.pk != request.user.branch_id:
        raise PermissionDenied("You can only work with your own branch.")
    return branch


def pharmacy_level_only(request):
    if request.user.is_branch_scoped:
        raise PermissionDenied("This area is restricted to pharmacy-level staff.")


def branch_filtered(qs, user, field="branch_id"):
    ids = branch_ids_for(user)
    return qs.filter(**{f"{field}__in": ids}) if ids else qs


# ---------------- suppliers ----------------
class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        exclude = ["tenant"]

    def validate_name(self, v):
        qs = Supplier.objects.filter(name__iexact=v.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A supplier with this name already exists.")
        return v.strip()

    def to_representation(self, obj):
        data = super().to_representation(obj)
        req = self.context.get("request")
        if req is not None and not req.user.has_tenant_perm("procurement.manage"):
            data.pop("payment_details", None)  # bank/mobile-money details are manage-level only
        return data


class SupplierListCreateView(Base, ListCreateAPIView):
    serializer_class = SupplierSerializer
    required_permissions = {"GET": "procurement.view", "POST": "procurement.manage"}
    search_fields = ["name", "company_name", "contact_person", "email"]
    filterset_fields = ["status"]

    def get_queryset(self):
        return Supplier.objects.all()

    def perform_create(self, s):
        sup = s.save()
        audit.record("procurement.supplier_created", actor=self.request.user, target=sup, request=self.request)


class SupplierDetailView(Base, RetrieveUpdateAPIView):
    serializer_class = SupplierSerializer
    required_permissions = {"GET": "procurement.view", "PATCH": "procurement.manage"}
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return Supplier.objects.all()

    def perform_update(self, s):
        sup = s.save()
        audit.record("procurement.supplier_updated", actor=self.request.user, target=sup, request=self.request, fields=sorted(s.validated_data))


# ---------------- requisitions ----------------
class ReqItemIn(serializers.Serializer):
    medicine = TenantPKField(Medicine)
    quantity = serializers.IntegerField(min_value=1)


class ReqIn(serializers.Serializer):
    branch = TenantPKField(Branch)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    items = ReqItemIn(many=True)
    submit = serializers.BooleanField(default=False)


def req_out(r):
    return {"id": r.pk, "number": r.number, "branch": r.branch_id, "status": r.status, "notes": r.notes, "requested_by": r.requested_by_id,
            "decision_note": r.decision_note, "created_at": r.created_at,
            "items": [{"medicine": i.medicine_id, "medicine_name": i.medicine.name, "quantity": i.quantity} for i in r.items.select_related("medicine")]}


class RequisitionListCreateView(Base, ListCreateAPIView):
    required_permissions = {"GET": "procurement.view", "POST": "procurement.manage"}
    filterset_fields = ["status", "branch"]
    search_fields = ["number"]

    def get_queryset(self):
        return branch_filtered(Requisition.objects.all(), self.request.user)

    def get_serializer_class(self):
        return ReqIn

    def list(self, request, *a, **k):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response([req_out(r) for r in page])

    def create(self, request, *a, **k):
        s = ReqIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        own_branch_only(request, d["branch"])
        r = services.create_requisition(branch=d["branch"], user=request.user, items=d["items"], notes=d["notes"], submit=d["submit"])
        return Response(req_out(r), status=201)


class ActionView(Base, APIView):
    """POST /<resource>/{id}/<action>/ — each action declares its permission and calls one service."""
    queryset_model = None
    required_permission = "procurement.manage"
    run = None
    out = None

    def post(self, request, pk):
        obj = get_object_or_404(branch_filtered(self.queryset_model.objects.all(), request.user), pk=pk)
        result = self.run(request, obj)
        return Response(self.out(result))


def _mk(name, model, perm, fn, out):
    return type(name, (ActionView,), {"queryset_model": model, "required_permission": perm, "run": staticmethod(fn), "out": staticmethod(out)})


RequisitionSubmit = _mk("RequisitionSubmit", Requisition, "procurement.manage", lambda r, o: services.submit_requisition(o.pk, user=r.user), req_out)
RequisitionApprove = _mk("RequisitionApprove", Requisition, "procurement.approve", lambda r, o: services.decide_requisition(o.pk, approve=True, user=r.user, note=str(r.data.get("note", ""))), req_out)
RequisitionReject = _mk("RequisitionReject", Requisition, "procurement.approve", lambda r, o: services.decide_requisition(o.pk, approve=False, user=r.user, note=str(r.data.get("note", ""))), req_out)
RequisitionCancel = _mk("RequisitionCancel", Requisition, "procurement.manage", lambda r, o: services.cancel_requisition(o.pk, user=r.user), req_out)


# ---------------- purchase orders ----------------
class POItemIn(serializers.Serializer):
    medicine = TenantPKField(Medicine)
    quantity = serializers.IntegerField(min_value=1)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


class POIn(serializers.Serializer):
    branch = TenantPKField(Branch)
    supplier = TenantPKField(Supplier)
    requisition = TenantPKField(Requisition, required=False, allow_null=True)
    expected_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    items = POItemIn(many=True)


def po_out(p):
    return {"id": p.pk, "number": p.number, "branch": p.branch_id, "supplier": p.supplier_id, "supplier_name": p.supplier.name,
            "status": p.status, "total": p.total, "expected_date": p.expected_date, "notes": p.notes, "created_by": p.created_by_id,
            "decision_note": p.decision_note, "created_at": p.created_at,
            "items": [{"id": i.pk, "medicine": i.medicine_id, "medicine_name": i.medicine.name, "quantity_ordered": i.quantity_ordered,
                       "quantity_received": i.quantity_received, "unit_cost": i.unit_cost} for i in p.items.select_related("medicine")]}


class OrderListCreateView(Base, ListCreateAPIView):
    required_permissions = {"GET": "procurement.view", "POST": "procurement.manage"}
    filterset_fields = ["status", "branch", "supplier"]
    search_fields = ["number", "supplier__name"]

    def get_queryset(self):
        return branch_filtered(PurchaseOrder.objects.select_related("supplier"), self.request.user)

    def get_serializer_class(self):
        return POIn

    def list(self, request, *a, **k):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response([po_out(p) for p in page])

    def create(self, request, *a, **k):
        s = POIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        own_branch_only(request, d["branch"])
        po = services.create_order(user=request.user, branch=d["branch"], supplier=d["supplier"], items=d["items"],
                                   expected_date=d.get("expected_date"), notes=d["notes"], requisition=d.get("requisition"))
        return Response(po_out(po), status=201)


class OrderDetailView(Base, APIView):
    required_permission = "procurement.view"

    def get(self, request, pk):
        return Response(po_out(get_object_or_404(branch_filtered(PurchaseOrder.objects.select_related("supplier"), request.user), pk=pk)))


OrderSubmit = _mk("OrderSubmit", PurchaseOrder, "procurement.manage", lambda r, o: services.submit_order(o.pk, user=r.user), po_out)
OrderApprove = _mk("OrderApprove", PurchaseOrder, "procurement.approve", lambda r, o: services.decide_order(o.pk, approve=True, user=r.user, note=str(r.data.get("note", ""))), po_out)
OrderReject = _mk("OrderReject", PurchaseOrder, "procurement.approve", lambda r, o: services.decide_order(o.pk, approve=False, user=r.user, note=str(r.data.get("note", ""))), po_out)
OrderCancel = _mk("OrderCancel", PurchaseOrder, "procurement.manage", lambda r, o: services.cancel_order(o.pk, user=r.user), po_out)


# ---------------- goods receipts ----------------
class GRNLineIn(serializers.Serializer):
    order_item = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    batch_number = serializers.CharField(max_length=60)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    selling_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)


class GRNIn(serializers.Serializer):
    order = TenantPKField(PurchaseOrder)
    delivery_note = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    lines = GRNLineIn(many=True)


def grn_out(g):
    return {"id": g.pk, "number": g.number, "order": g.order_id, "order_number": g.order.number, "branch": g.branch_id,
            "delivery_note": g.delivery_note, "created_at": g.created_at,
            "items": [{"medicine": i.batch.medicine_id, "batch_number": i.batch.batch_number, "quantity": i.quantity, "unit_cost": i.unit_cost,
                       "expiry_date": i.batch.expiry_date} for i in g.items.select_related("batch")]}


class GoodsReceiptView(Base, ListCreateAPIView):
    required_permissions = {"GET": "procurement.view", "POST": "procurement.manage"}
    filterset_fields = ["order", "branch"]

    def get_queryset(self):
        return branch_filtered(GoodsReceipt.objects.select_related("order"), self.request.user)

    def get_serializer_class(self):
        return GRNIn

    def list(self, request, *a, **k):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response([grn_out(g) for g in page])

    def create(self, request, *a, **k):
        s = GRNIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        own_branch_only(request, d["order"].branch)
        g = services.receive_goods(order_id=d["order"].pk, user=request.user, lines=d["lines"], delivery_note=d["delivery_note"], notes=d["notes"])
        return Response(grn_out(g), status=201)


# ---------------- supplier invoices / payments (pharmacy-level only) ----------------
class InvoiceSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    supplier = TenantPKField(Supplier)
    order = TenantPKField(PurchaseOrder, required=False, allow_null=True)

    class Meta:
        model = SupplierInvoice
        exclude = ["tenant", "created_by"]
        read_only_fields = ["amount_paid", "status"]


class InvoiceListCreateView(Base, ListCreateAPIView):
    serializer_class = InvoiceSerializer
    required_permissions = {"GET": "procurement.view", "POST": "procurement.manage"}
    filterset_fields = ["status", "supplier"]
    search_fields = ["invoice_number", "supplier__name"]

    def initial(self, request, *a, **k):
        super().initial(request, *a, **k)
        pharmacy_level_only(request)

    def get_queryset(self):
        return SupplierInvoice.objects.select_related("supplier")

    def create(self, request, *a, **k):
        s = InvoiceSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        d = s.validated_data
        inv_ = services.record_invoice(supplier=d["supplier"], invoice_number=d["invoice_number"].strip(), amount=d["amount"],
                                       due_date=d["due_date"], user=request.user, order=d.get("order"))
        return Response(InvoiceSerializer(inv_).data, status=201)


class PayInvoiceView(Base, APIView):
    required_permission = "accounting.manage"  # accountant / pharmacy admin

    def post(self, request, pk):
        pharmacy_level_only(request)
        get_object_or_404(SupplierInvoice, pk=pk)
        amount = serializers.DecimalField(max_digits=14, decimal_places=2).run_validation(request.data.get("amount"))
        p = services.pay_invoice(pk, amount=amount, method=str(request.data.get("method", "")), reference=str(request.data.get("reference", "")), user=request.user)
        return Response({"id": p.pk, "amount": p.amount, "reference": p.reference, "invoice_status": p.invoice.status, "outstanding": p.invoice.balance}, status=201)


class SupplierBalancesView(Base, APIView):
    required_permission = "procurement.view"

    def get(self, request):
        pharmacy_level_only(request)
        return Response(services.supplier_balances())


# ---------------- purchase returns ----------------
class PurchaseReturnView(Base, ListCreateAPIView):
    required_permissions = {"GET": "procurement.view", "POST": "procurement.manage"}
    pagination_class = None

    def get_serializer_class(self):
        class S(serializers.ModelSerializer):
            class Meta:
                model = PurchaseReturn
                exclude = ["tenant"]
        return S

    def get_queryset(self):
        return branch_filtered(PurchaseReturn.objects.select_related("batch"), self.request.user, "batch__branch_id")

    def create(self, request, *a, **k):
        from apps.inventory.selectors import scoped_batches
        b = get_object_or_404(scoped_batches(request.user), pk=request.data.get("batch"))
        qty = serializers.IntegerField(min_value=1).run_validation(request.data.get("quantity"))
        credit = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False).run_validation(request.data.get("credit_amount", 0))
        pr = services.return_to_supplier(batch_id=b.pk, quantity=qty, reason=str(request.data.get("reason", "")), user=request.user, credit_amount=credit)
        return Response(self.get_serializer(pr).data, status=201)
