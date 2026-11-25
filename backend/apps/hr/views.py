from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import HasTenantPermission, IsAuthenticatedAndSettled
from apps.audit import services as audit
from apps.core.fields import TenantPKField
from apps.core.views import TenantContextMixin
from apps.prescriptions.validators import validate_prescription_file
from apps.tenants.models import Branch

from . import services
from .models import AttendanceRecord, DisciplinaryRecord, LeaveRequest, LeaveType, StaffDocument, StaffProfile, WorkShift


class Base(TenantContextMixin):
    permission_classes = [HasTenantPermission]


class IsStaff(IsAuthenticatedAndSettled):
    def has_permission(self, request, view):
        u = request.user
        return super().has_permission(request, view) and not u.is_platform_admin and bool(u.role_id and u.role.code != "customer")


class SelfBase(TenantContextMixin):
    permission_classes = [IsStaff]


def paginate(request, qs, fn):
    pg = PageNumberPagination()
    return pg.get_paginated_response([fn(x) for x in pg.paginate_queryset(qs, request)])


def profile_out(p: StaffProfile, sensitive=False):
    u = p.user
    d = {"id": p.pk, "user": u.pk, "full_name": u.full_name, "email": u.email, "phone": u.phone, "role": u.role.name if u.role_id else None, "branch": u.branch_id,
         "staff_id": p.staff_id, "employment_date": p.employment_date, "employment_status": p.employment_status, "job_title": p.job_title, "department": p.department,
         "address": p.address, "emergency_contact_name": p.emergency_contact_name, "emergency_contact_phone": p.emergency_contact_phone,
         "terminated_on": p.terminated_on, "termination_reason": p.termination_reason if sensitive else ""}
    return d


# ---------------- staff records ----------------
class ProfileIn(serializers.Serializer):
    user = serializers.IntegerField(required=False)
    staff_id = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    employment_date = serializers.DateField(required=False)
    employment_status = serializers.ChoiceField(choices=["active", "on_leave", "suspended"], required=False)
    job_title = serializers.CharField(max_length=100, required=False, allow_blank=True)
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    emergency_contact_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    emergency_contact_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)


class StaffListView(Base, APIView):
    required_permissions = {"GET": "hr.view", "POST": "hr.manage"}

    def get(self, request):
        qs = services.staff_scope(request.user)
        if s := request.query_params.get("search"):
            qs = qs.filter(user__full_name__icontains=s) | qs.filter(staff_id__icontains=s)
        if st := request.query_params.get("status"):
            qs = qs.filter(employment_status=st)
        sens = request.user.has_tenant_perm("hr.sensitive")
        return paginate(request, qs.order_by("user__full_name"), lambda p: profile_out(p, sens))

    def post(self, request):
        s = ProfileIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        target = get_object_or_404(services.user_scope(request.user), pk=d.pop("user", None))
        if "employment_date" not in d:
            raise serializers.ValidationError({"employment_date": "This field is required."})
        p = services.create_profile(actor=request.user, target=target, **d)
        return Response(profile_out(p), status=201)


def get_profile(request, user_id):
    return get_object_or_404(services.staff_scope(request.user), user_id=user_id)


class StaffDetailView(Base, APIView):
    required_permissions = {"GET": "hr.view", "PATCH": "hr.manage"}

    def get(self, request, user_id):
        return Response(profile_out(get_profile(request, user_id), request.user.has_tenant_perm("hr.sensitive")))

    def patch(self, request, user_id):
        p = get_profile(request, user_id)
        s = ProfileIn(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if p.employment_status == "terminated":
            raise serializers.ValidationError({"detail": "This employment has ended."})
        for k in ("employment_status", "job_title", "department", "address", "emergency_contact_name", "emergency_contact_phone", "employment_date"):
            if k in d:
                setattr(p, k, d[k])
        p.save()
        audit.record("hr.profile_updated", actor=request.user, target=p, branch_id=p.user.branch_id, fields=sorted(d))
        return Response(profile_out(p))


class TerminateView(Base, APIView):
    required_permission = "hr.sensitive"

    def post(self, request, user_id):
        p = get_profile(request, user_id)
        on = serializers.DateField().run_validation(request.data.get("date") or str(timezone.localdate()))
        return Response(profile_out(services.terminate(p.pk, actor=request.user, on=on, reason=str(request.data.get("reason", ""))), True))


class DocumentsView(Base, APIView):
    required_permission = "hr.sensitive"
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, user_id):
        p = get_profile(request, user_id)
        return Response([{"id": d.pk, "type": d.doc_type, "title": d.title, "uploaded": d.created_at} for d in p.documents.all()])

    def post(self, request, user_id):
        p = get_profile(request, user_id)
        f = request.FILES.get("file")
        if f is None:
            raise serializers.ValidationError({"file": "Choose a file."})
        try:
            validate_prescription_file(f)
        except Exception as e:
            raise serializers.ValidationError({"file": list(getattr(e, "messages", [str(e)]))})
        d = StaffDocument.objects.create(profile=p, doc_type=str(request.data.get("doc_type", "other"))[:40], title=str(request.data.get("title", f.name))[:150], file=f, uploaded_by=request.user)
        audit.record("hr.document_uploaded", actor=request.user, target=d, branch_id=p.user.branch_id, staff=p.user_id)
        return Response({"id": d.pk}, status=201)


class DocumentDownloadView(Base, APIView):
    required_permission = "hr.sensitive"

    def get(self, request, pk):
        d = get_object_or_404(StaffDocument.objects.select_related("profile__user"), pk=pk, profile__in=services.staff_scope(request.user))
        audit.record("hr.document_viewed", actor=request.user, target=d, branch_id=d.profile.user.branch_id, request=request)
        resp = FileResponse(d.file.open("rb"), as_attachment=True, filename=f"{d.profile.staff_id}-{d.pk}{d.file.name[d.file.name.rfind('.'):]}")
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "private, no-store"
        return resp


class DisciplinaryView(Base, APIView):
    required_permission = "hr.sensitive"

    def get(self, request, user_id):
        p = get_profile(request, user_id)
        audit.record("hr.disciplinary_viewed", actor=request.user, target=p, branch_id=p.user.branch_id, request=request)
        return Response([{"id": r.pk, "date": r.date, "category": r.category, "description": r.description, "action_taken": r.action_taken} for r in p.disciplinary_records.all()])

    def post(self, request, user_id):
        p = get_profile(request, user_id)
        date = serializers.DateField().run_validation(request.data.get("date"))
        cat, desc = str(request.data.get("category", "")).strip(), str(request.data.get("description", "")).strip()
        if not cat or not desc:
            raise serializers.ValidationError({"detail": "Enter a category and a description."})
        r = DisciplinaryRecord.objects.create(profile=p, date=date, category=cat[:60], description=desc, action_taken=str(request.data.get("action_taken", ""))[:200], issued_by=request.user)
        audit.record("hr.disciplinary_recorded", actor=request.user, target=r, branch_id=p.user.branch_id, staff=p.user_id)
        return Response({"id": r.pk}, status=201)


# ---------------- attendance ----------------
def att_out(a):
    return {"id": a.pk, "user": a.user_id, "name": a.user.full_name, "date": a.date, "status": a.status, "clock_in": a.clock_in, "clock_out": a.clock_out, "source": a.source, "note": a.note}


class ClockView(SelfBase, APIView):
    out = False

    def post(self, request):
        rec = services.clock_out(request.user) if self.out else services.clock_in(request.user)
        return Response(att_out(rec), status=201)


class ClockOutView(ClockView):
    out = True


class AttendanceListView(Base, APIView):
    required_permission = "hr.view"

    def get(self, request):
        qs = AttendanceRecord.objects.filter(user__in=services.user_scope(request.user)).select_related("user")
        for k, f in (("date_from", "date__gte"), ("date_to", "date__lte"), ("user", "user_id"), ("status", "status")):
            if request.query_params.get(k):
                qs = qs.filter(**{f: request.query_params[k]})
        return paginate(request, qs, att_out)


class ManualAttendanceView(Base, APIView):
    required_permission = "hr.manage"

    def post(self, request):
        target = get_object_or_404(services.user_scope(request.user), pk=request.data.get("user"))
        on = serializers.DateField().run_validation(request.data.get("date"))
        ci = serializers.DateTimeField(required=False, allow_null=True).run_validation(request.data.get("clock_in") or None)
        co = serializers.DateTimeField(required=False, allow_null=True).run_validation(request.data.get("clock_out") or None)
        return Response(att_out(services.manual_attendance(actor=request.user, target=target, on=on, status=str(request.data.get("status", "")), clock_in=ci, clock_out=co, note=str(request.data.get("note", "")))), status=201)


# ---------------- work shifts ----------------
def shift_out(s):
    return {"id": s.pk, "user": s.user_id, "name": s.user.full_name, "branch": s.branch_id, "date": s.date, "start_time": s.start_time, "end_time": s.end_time, "notes": s.notes}


class ShiftsView(Base, APIView):
    required_permissions = {"GET": "hr.view", "POST": "hr.manage"}

    def get(self, request):
        qs = WorkShift.objects.filter(user__in=services.user_scope(request.user)).select_related("user")
        for k, f in (("date_from", "date__gte"), ("date_to", "date__lte"), ("user", "user_id")):
            if request.query_params.get(k):
                qs = qs.filter(**{f: request.query_params[k]})
        return paginate(request, qs, shift_out)

    def post(self, request):
        target = get_object_or_404(services.user_scope(request.user), pk=request.data.get("user"))
        branch = get_object_or_404(Branch, pk=request.data.get("branch") or target.branch_id)
        on = serializers.DateField().run_validation(request.data.get("date"))
        st, en = serializers.TimeField().run_validation(request.data.get("start_time")), serializers.TimeField().run_validation(request.data.get("end_time"))
        return Response(shift_out(services.schedule_shift(actor=request.user, target=target, branch=branch, on=on, start=st, end=en, notes=str(request.data.get("notes", "")))), status=201)


# ---------------- leave ----------------
def leave_out(l):
    return {"id": l.pk, "user": l.user_id, "name": l.user.full_name, "leave_type": l.leave_type.name, "paid": l.leave_type.is_paid, "start_date": l.start_date, "end_date": l.end_date,
            "days": l.days, "reason": l.reason, "status": l.status, "decision_note": l.decision_note}


class LeaveTypesView(Base, APIView):
    required_permissions = {"GET": "hr.view", "POST": "hr.sensitive"}

    def get(self, request):
        services.ensure_leave_types()
        return Response([{"id": t.pk, "name": t.name, "days_per_year": t.days_per_year, "is_paid": t.is_paid, "is_active": t.is_active} for t in LeaveType.objects.all()])

    def post(self, request):
        name = str(request.data.get("name", "")).strip()
        if not name or LeaveType.objects.filter(name__iexact=name).exists():
            raise serializers.ValidationError({"name": "Enter a unique leave type name."})
        t = LeaveType.objects.create(name=name[:60], days_per_year=int(request.data.get("days_per_year", 0)), is_paid=bool(request.data.get("is_paid", True)))
        return Response({"id": t.pk, "name": t.name}, status=201)


class LeaveListView(Base, APIView):
    required_permission = "hr.view"

    def get(self, request):
        qs = LeaveRequest.objects.filter(user__in=services.user_scope(request.user)).select_related("user", "leave_type")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return paginate(request, qs, leave_out)


class LeaveDecideView(Base, APIView):
    required_permission = "hr.manage"
    approve = True

    def post(self, request, pk):
        lr = get_object_or_404(LeaveRequest.objects.filter(user__in=services.user_scope(request.user)), pk=pk)
        return Response(leave_out(services.decide_leave(lr.pk, actor=request.user, approve=self.approve, note=str(request.data.get("note", "")))))


class LeaveRejectView(LeaveDecideView):
    approve = False


# ---------------- self service ----------------
class MeView(SelfBase, APIView):
    def get(self, request):
        p = StaffProfile.objects.select_related("user", "user__role").filter(user=request.user).first()
        return Response(profile_out(p) if p else {"user": request.user.pk, "full_name": request.user.full_name, "note": "No HR record yet."})

    def patch(self, request):
        p = get_object_or_404(StaffProfile, user=request.user)
        u = request.user
        for k in ("phone",):
            if k in request.data:
                setattr(u, k, str(request.data[k])[:30])
        u.save(update_fields=["phone"])
        for k, n in (("address", 255), ("emergency_contact_name", 150), ("emergency_contact_phone", 30)):  # job title, status and employment dates are HR-controlled
            if k in request.data:
                setattr(p, k, str(request.data[k])[:n])
        p.save()
        audit.record("hr.self_profile_updated", actor=u, target=p, fields=sorted(set(request.data) & {"phone", "address", "emergency_contact_name", "emergency_contact_phone"}))
        return Response(profile_out(p))


class MyAttendanceView(SelfBase, APIView):
    def get(self, request):
        return paginate(request, AttendanceRecord.objects.filter(user=request.user).select_related("user"), att_out)


class MyShiftsView(SelfBase, APIView):
    def get(self, request):
        return paginate(request, WorkShift.objects.filter(user=request.user, date__gte=timezone.localdate()).select_related("user"), shift_out)


class MyLeaveView(SelfBase, APIView):
    def get(self, request):
        services.ensure_leave_types()
        return Response({"balances": [services.balance(request.user, t) for t in LeaveType.objects.filter(is_active=True)],
                         "requests": [leave_out(l) for l in LeaveRequest.objects.filter(user=request.user).select_related("user", "leave_type")[:50]]})

    def post(self, request):
        services.ensure_leave_types()
        t = get_object_or_404(LeaveType, pk=request.data.get("leave_type"))
        start, end = serializers.DateField().run_validation(request.data.get("start_date")), serializers.DateField().run_validation(request.data.get("end_date"))
        return Response(leave_out(services.request_leave(user=request.user, leave_type=t, start=start, end=end, reason=str(request.data.get("reason", "")))), status=201)


class MyLeaveCancelView(SelfBase, APIView):
    def post(self, request, pk):
        get_object_or_404(LeaveRequest, pk=pk, user=request.user)
        return Response(leave_out(services.cancel_leave(pk, actor=request.user)))
