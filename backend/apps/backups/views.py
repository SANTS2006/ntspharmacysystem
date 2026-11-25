from django.db import connection, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformAdmin
from apps.audit import services as audit

from . import services
from .models import BackupRecord, RestoreRequest


def rec_out(r: BackupRecord):
    return {"id": r.pk, "number": r.number, "kind": r.kind, "status": r.status, "started_at": r.started_at, "finished_at": r.finished_at, "size_bytes": r.size_bytes,
            "verified_at": r.verified_at, "verification": r.verification, "retention_until": r.retention_until, "error": r.error, "objects": sum(r.object_counts.values()) if r.object_counts else 0,
            "created_by": r.created_by.email if r.created_by else None}


def req_out(r: RestoreRequest):
    return {"id": r.pk, "backup": r.backup.number, "backup_id": r.backup_id, "reason": r.reason, "status": r.status, "requested_by": r.requested_by.email if r.requested_by else None,
            "approved_by": r.approved_by.email if r.approved_by else None, "expires_at": r.expires_at, "created_at": r.created_at, "started_at": r.started_at, "finished_at": r.finished_at,
            "log": r.log, "error": r.error, "confirmation_phrase": services.phrase(r) if r.status == "approved" else None}


class BackupsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        pg = PageNumberPagination()
        return pg.get_paginated_response([rec_out(r) for r in pg.paginate_queryset(BackupRecord.objects.select_related("created_by"), request)])

    def post(self, request):
        r = services.run_backup(kind="manual", user=request.user, request=request)
        return Response(rec_out(r), status=201 if r.status == "completed" else 500)


class BackupHealthView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response(services.health())


class BackupVerifyView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        get_object_or_404(BackupRecord, pk=pk)
        return Response(rec_out(services.verify_backup(pk, user=request.user)))


class BackupDownloadView(APIView):
    """The ENCRYPTED object, proxied through the server (no storage URL is ever revealed). Useless without BACKUP_ENCRYPTION_KEY, which is never available here."""
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk):
        rec = get_object_or_404(BackupRecord, pk=pk)
        data = services.read_encrypted(rec)
        audit.record("backup.downloaded", actor=request.user, request=request, backup=rec.number)
        r = HttpResponse(data, content_type="application/octet-stream")
        r["Content-Disposition"] = f'attachment; filename="{rec.number}.bak.enc"'
        r["X-Content-Type-Options"] = "nosniff"
        r["Cache-Control"] = "private, no-store"
        return r


class RestoresView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        for r in RestoreRequest.objects.filter(status__in=["pending", "approved"]):
            services._fresh(r)
        return Response([req_out(r) for r in RestoreRequest.objects.select_related("backup", "requested_by", "approved_by")[:50]])

    def post(self, request):
        req = services.request_restore(user=request.user, backup_id=request.data.get("backup"), reason=str(request.data.get("reason", "")), password=str(request.data.get("password", "")))
        return Response(req_out(req), status=201)


class RestoreApproveView(APIView):
    permission_classes = [IsPlatformAdmin]
    approve = True

    def post(self, request, pk):
        get_object_or_404(RestoreRequest, pk=pk)
        return Response(req_out(services.approve_restore(pk, user=request.user, password=str(request.data.get("password", "")), approve=self.approve)))


class RestoreRejectView(RestoreApproveView):
    approve = False


class RestoreExecuteView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        get_object_or_404(RestoreRequest, pk=pk)
        req = services.execute_restore(pk, user=request.user, password=str(request.data.get("password", "")), confirmation=str(request.data.get("confirmation", "")))
        return Response(req_out(req), status=200 if req.status == "completed" else 500)


# ---------------- health checks for load balancers (no auth, no data) ----------------
@transaction.non_atomic_requests  # a database outage must produce a clean 503, not a failed transaction start
def live(request):
    return JsonResponse({"status": "ok"})


@transaction.non_atomic_requests
def ready(request):
    checks = {}
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        from django.core.cache import cache
        cache.set("health", "1", 5)
        checks["cache"] = "ok" if cache.get("health") == "1" else "error"
    except Exception:
        checks["cache"] = "error"
    ok = all(v == "ok" for v in checks.values())
    return JsonResponse({"status": "ok" if ok else "degraded", "checks": checks}, status=200 if ok else 503)
