from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission
from apps.core.views import TenantContextMixin
from apps.medicines.models import Medicine
from apps.medicines.views import MedicineSerializer
from apps.tenants.models import Branch

from . import selectors, services
from .models import Batch, StockMovement, StockTransfer


class BatchSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    is_expired = serializers.SerializerMethodField()
    saleable = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        exclude = ["tenant"]

    def get_is_expired(self, b):
        return services.is_expired(b)

    def get_saleable(self, b):
        return b.status == Batch.Status.AVAILABLE and b.quantity_available > 0 and not services.is_expired(b)


class MovementSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.name", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True, default=None)

    class Meta:
        model = StockMovement
        exclude = ["tenant"]


def branch_for(request, branch):
    """Branch-scoped users may only act on their own branch."""
    if request.user.is_branch_scoped and branch.pk != request.user.branch_id:
        raise PermissionDenied("You can only manage inventory of your own branch.")
    return branch


def get_batch(request, pk):
    return get_object_or_404(selectors.scoped_batches(request.user), pk=pk)


class InvView(TenantContextMixin):
    permission_classes = [HasTenantPermission]


class BatchListView(InvView, ListAPIView):
    serializer_class = BatchSerializer
    required_permission = "inventory.view"
    search_fields = ["batch_number", "medicine__name", "medicine__barcode"]
    filterset_fields = {"branch": ["exact"], "medicine": ["exact"], "status": ["exact"], "expiry_date": ["lte", "gte"]}
    ordering_fields = ["expiry_date", "created_at", "quantity_available"]

    def get_queryset(self):
        return selectors.scoped_batches(self.request.user)


class MovementListView(InvView, ListAPIView):
    serializer_class = MovementSerializer
    required_permission = "inventory.view"
    filterset_fields = ["medicine", "batch", "branch", "movement_type"]

    def get_queryset(self):
        qs = StockMovement.objects.select_related("medicine", "batch", "user")
        ids = selectors.branch_ids_for(self.request.user)
        return qs.filter(branch_id__in=ids) if ids else qs


class OverviewView(InvView, ListAPIView):
    serializer_class = MedicineSerializer
    required_permission = "inventory.view"
    search_fields = ["name", "generic_name", "barcode", "sku"]
    filterset_fields = ["category", "classification"]

    def get_queryset(self):
        return selectors.medicines_with_stock(self.request.user, self.request.query_params.get("branch")).filter(status="active")


class AlertsView(InvView, APIView):
    required_permission = "inventory.view"

    def get(self, request):
        days = int((request.tenant.settings or {}).get("expiry_alert_days", 90))
        a = selectors.alerts(request.user, days)
        return Response({
            "near_expiry_days": days,
            "low_stock": MedicineSerializer(a["low_stock"][:100], many=True).data,
            "out_of_stock": MedicineSerializer(a["out_of_stock"][:100], many=True).data,
            "near_expiry": BatchSerializer(a["near_expiry"][:100], many=True).data,
            "expired": BatchSerializer(a["expired"][:100], many=True).data,
        })


class ValuationView(InvView, APIView):
    required_permission = "inventory.view"

    def get(self, request):
        return Response(selectors.valuation(request.user))


# ---------------- writes (inventory.manage) ----------------
class ReceiveSerializer(serializers.Serializer):
    # Querysets are bound per instance: a class-level Medicine.objects.all() would be evaluated at import time,
    # with no tenant context, and (fail-closed) match nothing.
    medicine = serializers.PrimaryKeyRelatedField(queryset=Medicine.all_objects.none())
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.all_objects.none())

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["medicine"].queryset = Medicine.objects.all()
        self.fields["branch"].queryset = Branch.objects.all()
    batch_number = serializers.CharField(max_length=60)
    quantity = serializers.IntegerField(min_value=1)
    purchase_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    purchase_date = serializers.DateField(required=False)
    manufacturing_date = serializers.DateField(required=False, allow_null=True)
    supplier_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    selling_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)
    storage_location = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class ReceiveView(InvView, APIView):
    required_permission = "inventory.manage"

    def post(self, request):
        s = ReceiveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        branch_for(request, d["branch"])
        batch = services.receive_stock(user=request.user, **d)
        return Response(BatchSerializer(batch).data, status=201)


class AdjustView(InvView, APIView):
    required_permission = "inventory.manage"

    def post(self, request, pk):
        b = get_batch(request, pk)
        s = serializers.Serializer(data=request.data)
        n = serializers.IntegerField(min_value=0).run_validation(request.data.get("new_quantity"))
        out = services.adjust_stock(batch_id=b.pk, new_quantity=n, reason=str(request.data.get("reason", "")), user=request.user)
        return Response(BatchSerializer(out).data)


class WriteOffView(InvView, APIView):
    required_permission = "inventory.manage"

    def post(self, request, pk):
        b = get_batch(request, pk)
        q = request.data.get("quantity")
        out = services.write_off(batch_id=b.pk, kind=str(request.data.get("kind", "")), reason=str(request.data.get("reason", "")),
                                 user=request.user, quantity=int(q) if q else None)
        return Response(BatchSerializer(out).data)


class BatchStatusView(InvView, APIView):
    required_permission = "inventory.manage"

    def post(self, request, pk):
        b = get_batch(request, pk)
        out = services.set_batch_status(batch_id=b.pk, status=str(request.data.get("status", "")), reason=str(request.data.get("reason", "")), user=request.user)
        return Response(BatchSerializer(out).data)


class RecallView(InvView, APIView):
    """Pharmacy-wide recall by manufacturer batch number: pharmacy-level staff only."""
    required_permission = "inventory.manage"

    def post(self, request):
        if request.user.is_branch_scoped:
            raise PermissionDenied("Only pharmacy-level staff can recall a batch across branches.")
        m = get_object_or_404(Medicine, pk=request.data.get("medicine"))
        n = services.recall_batch_number(medicine=m, batch_number=str(request.data.get("batch_number", "")).strip(),
                                         reason=str(request.data.get("reason", "")), user=request.user)
        return Response({"recalled_batches": n})


class TransferView(InvView, ListAPIView):
    required_permissions = {"GET": "inventory.view", "POST": "inventory.manage"}
    pagination_class = None

    def get_serializer_class(self):
        class S(serializers.ModelSerializer):
            class Meta:
                model = StockTransfer
                exclude = ["tenant"]
        return S

    def get_queryset(self):
        qs = StockTransfer.objects.all()
        ids = selectors.branch_ids_for(self.request.user)
        return qs.filter(from_branch_id__in=ids) if ids else qs

    def post(self, request):
        b = get_batch(request, request.data.get("batch"))
        to = get_object_or_404(Branch, pk=request.data.get("to_branch"))
        qty = serializers.IntegerField(min_value=1).run_validation(request.data.get("quantity"))
        t = services.transfer_stock(batch_id=b.pk, to_branch=to, quantity=qty, user=request.user, reason=str(request.data.get("reason", "")))
        return Response(self.get_serializer(t).data, status=201)
