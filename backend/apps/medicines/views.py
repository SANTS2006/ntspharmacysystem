import re

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission
from apps.audit import services as audit
from apps.core.views import TenantContextMixin
from apps.inventory.selectors import medicines_with_stock

from .models import Category, Medicine

BARCODE_RE = re.compile(r"^[A-Za-z0-9-]{6,32}$")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip()
        qs = Category.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        return value


class MedicineSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True)
    requires_prescription = serializers.BooleanField(read_only=True)

    class Meta:
        model = Medicine
        exclude = ["tenant"]
        read_only_fields = ["id", "status", "created_at", "updated_at"]
        extra_kwargs = {**{f: {"min_value": 0} for f in ("purchase_price", "selling_price", "wholesale_price")},
                        "tax_rate": {"min_value": 0, "max_value": 100}}

    def get_stock(self, obj):  # saleable quantity across the caller's visible branches (annotated)
        return getattr(obj, "stock", None)

    def _unique(self, field, value):
        if not value:
            return value
        qs = Medicine.objects.filter(**{field: value})
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"This {field} is already used by another medicine.")
        return value

    def validate_barcode(self, v):
        v = v.strip()
        if v and not BARCODE_RE.match(v):
            raise serializers.ValidationError("Barcode must be 6-32 letters, numbers or hyphens.")
        return self._unique("barcode", v)

    def validate_sku(self, v):
        return self._unique("sku", v.strip())

    def validate(self, attrs):
        cls = attrs.get("classification", getattr(self.instance, "classification", Medicine.Classification.OTC))
        if cls == Medicine.Classification.CONTROLLED:
            attrs["is_online_visible"] = False  # controlled medicines are never listed online
        if cls != Medicine.Classification.OTC:
            reg = attrs.get("registration_number", getattr(self.instance, "registration_number", ""))
            if not reg:
                raise serializers.ValidationError({"registration_number": "A registration number is required for prescription and controlled medicines."})
        return attrs


class MedicineListCreateView(TenantContextMixin, ListCreateAPIView):
    serializer_class = MedicineSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "medicine.view", "POST": "medicine.manage"}
    search_fields = ["name", "generic_name", "brand_name", "barcode", "sku", "active_ingredient"]
    filterset_fields = ["category", "classification", "status", "dosage_form"]
    ordering_fields = ["name", "selling_price", "created_at", "stock"]

    def get_queryset(self):
        return medicines_with_stock(self.request.user)

    def perform_create(self, serializer):
        m = serializer.save()
        audit.record("medicine.created", actor=self.request.user, target=m, request=self.request, name=m.name)


class MedicineDetailView(TenantContextMixin, RetrieveUpdateAPIView):
    serializer_class = MedicineSerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "medicine.view", "PATCH": "medicine.manage"}
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return medicines_with_stock(self.request.user)

    def perform_update(self, serializer):
        m = serializer.save()
        audit.record("medicine.updated", actor=self.request.user, target=m, request=self.request, fields=sorted(serializer.validated_data))


class MedicineStatusView(TenantContextMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permission = "medicine.manage"
    archive = True

    def post(self, request, pk):
        m = get_object_or_404(Medicine, pk=pk)
        if self.archive:
            from apps.inventory.models import Batch
            if Batch.objects.filter(medicine=m, quantity_available__gt=0).exists():
                raise ValidationError({"detail": "This medicine still has stock on hand. Write it off or transfer it first."})
            m.status = Medicine.Status.ARCHIVED
        else:
            m.status = Medicine.Status.ACTIVE
        m.save(update_fields=["status", "updated_at"])
        audit.record("medicine.archived" if self.archive else "medicine.restored", actor=request.user, target=m, request=request)
        return Response(MedicineSerializer(m).data)


class MedicineRestoreView(MedicineStatusView):
    archive = False


class BarcodeLookupView(TenantContextMixin, APIView):
    permission_classes = [HasTenantPermission]
    required_permission = "medicine.view"

    def get(self, request, code):
        m = medicines_with_stock(request.user).filter(barcode=code, status="active").first()
        if m is None:
            return Response({"success": False, "error": {"code": "not_found", "message": "No medicine matches this barcode.", "details": None}}, status=404)
        return Response(MedicineSerializer(m).data)


class CategoryListCreateView(TenantContextMixin, ListCreateAPIView):
    serializer_class = CategorySerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "medicine.view", "POST": "medicine.manage"}
    pagination_class = None

    def get_queryset(self):
        return Category.objects.all()


class CategoryDetailView(TenantContextMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = CategorySerializer
    permission_classes = [HasTenantPermission]
    required_permissions = {"GET": "medicine.view", "PATCH": "medicine.manage", "DELETE": "medicine.manage"}
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Category.objects.all()

    def perform_destroy(self, instance):
        if instance.medicines.exists():
            raise ValidationError({"detail": "A category with medicines in it cannot be deleted."})
        instance.delete()
