from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantPermission
from apps.audit import services as audit
from apps.core.fields import TenantPKField
from apps.core.views import TenantContextMixin
from apps.inventory.selectors import branch_ids_for
from apps.medicines.models import Medicine
from apps.tenants.models import Branch

from . import services
from .models import (ControlledDrugRegisterEntry, DrugInteraction, Patient, Prescription)
from .validators import validate_prescription_file


class Base(TenantContextMixin):
    permission_classes = [HasTenantPermission]


def rx_queryset(user):
    qs = Prescription.objects.select_related("patient", "branch")
    ids = branch_ids_for(user)
    return qs.filter(branch_id__in=ids) if ids else qs


def patient_queryset(user):
    ids = branch_ids_for(user)
    qs = Patient.objects.all()
    return qs.filter(Q(branch_id__in=ids) | Q(prescriptions__branch_id__in=ids)).distinct() if ids else qs


# ---------------- patients ----------------
class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        exclude = ["tenant", "user", "branch"]

    def validate_allergies(self, v):
        if not isinstance(v, list) or any(not isinstance(a, str) or not a.strip() or len(a) > 100 for a in v) or len(v) > 50:
            raise serializers.ValidationError("Provide a list of allergy names.")
        return [a.strip() for a in v]


class PatientListCreateView(Base, ListCreateAPIView):
    serializer_class = PatientSerializer
    required_permissions = {"GET": "prescription.view", "POST": "prescription.register"}
    search_fields = ["full_name", "phone"]

    def get_queryset(self):
        return patient_queryset(self.request.user)

    def perform_create(self, s):
        u = self.request.user
        p = s.save(branch=Branch.objects.filter(pk=u.branch_id).first() if u.branch_id else None)
        audit.record("patient.created", actor=u, target=p, request=self.request, branch_id=u.branch_id)


class PatientDetailView(Base, RetrieveUpdateAPIView):
    serializer_class = PatientSerializer
    required_permissions = {"GET": "prescription.view", "PATCH": "prescription.register"}
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return patient_queryset(self.request.user)

    def perform_update(self, s):
        p = s.save()
        audit.record("patient.updated", actor=self.request.user, target=p, request=self.request, fields=sorted(s.validated_data))


# ---------------- prescriptions ----------------
class ItemIn(serializers.Serializer):
    medicine = TenantPKField(Medicine)
    dosage = serializers.CharField(max_length=100)
    frequency = serializers.CharField(max_length=100)
    duration_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    quantity_prescribed = serializers.IntegerField(min_value=1)
    instructions = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class RxIn(serializers.Serializer):
    patient = TenantPKField(Patient)
    branch = TenantPKField(Branch)
    prescriber_name = serializers.CharField(max_length=200)
    prescriber_registration = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    facility = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    external_reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    prescription_date = serializers.DateField()
    expiry_date = serializers.DateField(required=False, allow_null=True)
    refills_allowed = serializers.IntegerField(min_value=0, max_value=12, default=0)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    items = ItemIn(many=True)


def rx_out(rx, detail=False):
    d = {"id": rx.pk, "reference_number": rx.reference_number, "external_reference": rx.external_reference,
         "status": services.effective_status(rx), "patient": rx.patient_id, "patient_name": rx.patient.full_name, "branch": rx.branch_id,
         "prescriber_name": rx.prescriber_name, "prescriber_registration": rx.prescriber_registration, "facility": rx.facility,
         "prescription_date": rx.prescription_date, "expiry_date": rx.expiry_date, "refills_allowed": rx.refills_allowed,
         "refills_used": rx.refills_used, "has_document": bool(rx.document), "created_at": rx.created_at,
         "rejection_reason": rx.rejection_reason}
    if detail:
        d["patient_allergies"] = rx.patient.allergies
        d["items"] = [{"id": i.pk, "medicine": i.medicine_id, "medicine_name": i.medicine.name, "classification": i.medicine.classification,
                       "dosage": i.dosage, "frequency": i.frequency, "duration_days": i.duration_days, "quantity_prescribed": i.quantity_prescribed,
                       "quantity_dispensed": i.quantity_dispensed, "instructions": i.instructions} for i in rx.items.select_related("medicine")]
        d["safety_alerts"] = [{"id": a.pk, "type": a.alert_type, "severity": a.severity, "message": a.message, "source": "system",
                               "decision": a.decision, "decision_note": a.decision_note, "decided_by": a.decided_by.email if a.decided_by else None}
                              for a in rx.alerts.select_related("decided_by")]
        d["interventions"] = [{"id": i.pk, "type": i.intervention_type, "note": i.note, "outcome": i.outcome, "pharmacist": i.pharmacist.email if i.pharmacist else None, "at": i.created_at} for i in rx.interventions.select_related("pharmacist")]
        d["dispensings"] = [{"id": x.pk, "at": x.created_at, "by": x.dispensed_by.email if x.dispensed_by else None, "refill_number": x.refill_number,
                             "items": [{"medicine": di.item.medicine.name, "batch": di.batch.batch_number, "quantity": di.quantity} for di in x.items.select_related("item__medicine", "batch")]}
                            for x in rx.dispensings.select_related("dispensed_by")]
        d["availability"] = services.availability(rx)
    return d


class PrescriptionListCreateView(Base, ListCreateAPIView):
    required_permissions = {"GET": "prescription.view", "POST": "prescription.register"}
    filterset_fields = ["status", "branch", "patient"]
    search_fields = ["reference_number", "external_reference", "patient__full_name", "prescriber_name"]

    def get_queryset(self):
        return rx_queryset(self.request.user)

    def get_serializer_class(self):
        return RxIn

    def list(self, request, *a, **k):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response([rx_out(r) for r in page])

    def create(self, request, *a, **k):
        s = RxIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        branch, patient = d.pop("branch"), d.pop("patient")
        if request.user.is_branch_scoped and branch.pk != request.user.branch_id:
            raise PermissionDenied("You can only register prescriptions for your own branch.")
        if not patient_queryset(request.user).filter(pk=patient.pk).exists():
            raise serializers.ValidationError({"patient": "Select a valid patient."})
        items = d.pop("items")
        rx = services.create_prescription(patient=patient, branch=branch, user=request.user, items=items, **d)
        return Response(rx_out(rx, True), status=201)


class PrescriptionDetailView(Base, APIView):
    required_permission = "prescription.view"

    def get(self, request, pk):
        rx = get_object_or_404(rx_queryset(request.user), pk=pk)
        audit.record("prescription.viewed", actor=request.user, target=rx, branch_id=rx.branch_id, request=request)  # PHI access trail
        return Response(rx_out(rx, True))


class DocumentView(Base, APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    required_permissions = {"GET": "prescription.view", "POST": "prescription.register"}

    def get(self, request, pk):
        rx = get_object_or_404(rx_queryset(request.user), pk=pk)
        if not rx.document:
            raise NotFound("No document attached.")
        audit.record("prescription.document_viewed", actor=request.user, target=rx, branch_id=rx.branch_id, request=request)
        resp = FileResponse(rx.document.open("rb"), as_attachment=True, filename=f"{rx.reference_number}{rx.document.name[rx.document.name.rfind('.'):]}")
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "private, no-store"
        return resp

    def post(self, request, pk):
        rx = get_object_or_404(rx_queryset(request.user), pk=pk)
        f = request.FILES.get("document")
        if f is None:
            raise serializers.ValidationError({"document": "Choose a file."})
        try:
            validate_prescription_file(f)
        except Exception as e:  # django ValidationError -> API 400
            raise serializers.ValidationError({"document": list(getattr(e, "messages", [str(e)]))})
        if rx.status not in services.LIVE:
            raise serializers.ValidationError({"detail": "Documents can only be attached to open prescriptions."})
        rx.document.save(f"{rx.reference_number}-{f.name}"[:100], f)
        audit.record("prescription.document_attached", actor=request.user, target=rx, branch_id=rx.branch_id, request=request)
        return Response(rx_out(rx), status=201)


class RxAction(Base, APIView):
    required_permission = "prescription.verify"
    fn = None

    def post(self, request, pk):
        rx = get_object_or_404(rx_queryset(request.user), pk=pk)
        self.fn(request, rx)
        rx.refresh_from_db()
        return Response(rx_out(rx, True))


def _act(name, perm, fn):
    return type(name, (RxAction,), {"required_permission": perm, "fn": staticmethod(fn)})


StartReview = _act("StartReview", "prescription.verify", lambda r, x: services.start_review(x.pk, user=r.user))
Recheck = _act("Recheck", "prescription.verify", lambda r, x: services.recheck_safety(x.pk, user=r.user))
Approve = _act("Approve", "prescription.verify", lambda r, x: services.approve(x.pk, user=r.user, checklist=r.data.get("verification") or {}))
Reject = _act("Reject", "prescription.verify", lambda r, x: services.reject(x.pk, user=r.user, reason=str(r.data.get("reason", ""))))
Cancel = _act("Cancel", "prescription.verify", lambda r, x: services.cancel(x.pk, user=r.user, reason=str(r.data.get("reason", ""))))
Refill = _act("Refill", "prescription.dispense", lambda r, x: services.refill(x.pk, user=r.user))


class LineIn(serializers.Serializer):
    item = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class DispenseView(Base, APIView):
    required_permission = "prescription.dispense"

    def post(self, request, pk):
        rx = get_object_or_404(rx_queryset(request.user), pk=pk)
        s = LineIn(data=request.data.get("lines") or [], many=True)
        s.is_valid(raise_exception=True)
        services.dispense(rx.pk, user=request.user, lines=s.validated_data, notes=str(request.data.get("notes", "")))
        rx.refresh_from_db()
        return Response(rx_out(rx, True), status=201)


class AcknowledgeAlertView(Base, APIView):
    required_permission = "prescription.verify"

    def post(self, request, pk, alert_id):
        rx = get_object_or_404(rx_queryset(request.user), pk=pk)
        get_object_or_404(rx.alerts.all(), pk=alert_id)
        services.acknowledge_alert(rx.pk, alert_id, user=request.user, note=str(request.data.get("note", "")))
        return Response(rx_out(rx, True))


class InterventionView(Base, APIView):
    required_permission = "prescription.verify"

    def post(self, request, pk):
        rx = get_object_or_404(rx_queryset(request.user), pk=pk)
        services.record_intervention(rx.pk, user=request.user, intervention_type=str(request.data.get("type", "")),
                                     note=str(request.data.get("note", "")), outcome=str(request.data.get("outcome", "")))
        return Response(rx_out(rx, True), status=201)


# ---------------- pharmacy-maintained interaction table / controlled register ----------------
class InteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrugInteraction
        exclude = ["tenant"]

    def validate(self, a):
        if a.get("ingredient_a", "").strip().lower() == a.get("ingredient_b", "").strip().lower():
            raise serializers.ValidationError("Choose two different ingredients.")
        return a


class InteractionListCreateView(Base, ListCreateAPIView):
    serializer_class = InteractionSerializer
    required_permissions = {"GET": "medicine.view", "POST": "medicine.manage"}
    search_fields = ["ingredient_a", "ingredient_b"]

    def get_queryset(self):
        return DrugInteraction.objects.all()

    def perform_create(self, s):
        r = s.save()
        audit.record("prescription.interaction_rule_created", actor=self.request.user, target=r, request=self.request)


class InteractionDetailView(Base, RetrieveUpdateDestroyAPIView):
    serializer_class = InteractionSerializer
    required_permissions = {"GET": "medicine.view", "PATCH": "medicine.manage", "DELETE": "medicine.manage"}
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return DrugInteraction.objects.all()


class ControlledRegisterView(Base, ListAPIView):
    required_permission = "prescription.verify"

    def get_serializer_class(self):
        class S(serializers.ModelSerializer):
            medicine_name = serializers.CharField(source="medicine.name", read_only=True)
            batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
            pharmacist_email = serializers.CharField(source="pharmacist.email", read_only=True, default=None)

            class Meta:
                model = ControlledDrugRegisterEntry
                exclude = ["tenant"]
        return S

    def get_queryset(self):
        qs = ControlledDrugRegisterEntry.objects.select_related("medicine", "batch", "pharmacist")
        ids = branch_ids_for(self.request.user)
        return qs.filter(prescription__branch_id__in=ids) if ids else qs
