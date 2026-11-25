from datetime import date

from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAuthenticatedAndSettled
from apps.audit import services as audit
from apps.core.views import TenantContextMixin
from apps.tenants.models import Branch

from . import dashboard, exports, reports


class ReportBase(TenantContextMixin, APIView):
    permission_classes = [IsAuthenticatedAndSettled]

    def allowed(self, user, slug):
        perms = reports.REGISTRY[slug][2]
        return not user.is_platform_admin and any(user.has_tenant_perm(p) for p in perms)

    def params(self, request) -> "reports.P":
        q = request.query_params
        d = lambda k: serializers.DateField().run_validation(q[k]) if q.get(k) else None  # noqa: E731
        f, t = d("date_from"), d("date_to")
        if f and t and f > t:
            raise serializers.ValidationError({"date_from": "The start date must not be after the end date."})
        branch = q.get("branch")
        if request.user.is_branch_scoped:  # branch managers can only ever report on their own branch
            if branch and str(branch) != str(request.user.branch_id):
                raise PermissionDenied("You can only report on your own branch.")
            branch = request.user.branch_id
        if branch and not Branch.objects.filter(pk=branch).exists():
            raise NotFound()
        days = max(1, min(int(q.get("days", 90)), 730)) if str(q.get("days", "90")).isdigit() else 90
        return reports.P(f, t, int(branch) if branch else None, q.get("group", "day"), days)


class ReportListView(ReportBase):
    def get(self, request):
        out = [{"slug": s, "title": v[0], "group": v[1]} for s, v in reports.REGISTRY.items() if self.allowed(request.user, s)]
        if not out:
            raise PermissionDenied("You have no reports available.")
        return Response(out)


class ReportView(ReportBase):
    def get(self, request, slug):
        if slug not in reports.REGISTRY:
            raise NotFound()
        if not self.allowed(request.user, slug):
            raise PermissionDenied("You are not allowed to run this report.")
        title, _, _, fn = reports.REGISTRY[slug]
        p = self.params(request)
        columns, rows, summary = fn(p)
        q = request.query_params
        if s := (q.get("search") or "").strip().lower():
            rows = [r for r in rows if any(s in str(v).lower() for v in r.values() if isinstance(v, (str, int)))]
        if o := q.get("ordering"):
            key = o.lstrip("-")
            if key not in {c["key"] for c in columns}:
                raise serializers.ValidationError({"ordering": "Unknown column."})
            rows = sorted(rows, key=lambda r: (r.get(key) is None, r.get(key)), reverse=o.startswith("-"))  # type: ignore[arg-type]
        fmt = q.get("export", "json")  # NOT "format": DRF reserves ?format= for renderer selection
        meta = {"slug": slug, "title": title, "date_from": p.date_from, "date_to": p.date_to, "branch": p.branch}
        if fmt == "json":
            size = max(1, min(int(q.get("page_size", 50)), 200)) if str(q.get("page_size", "50")).isdigit() else 50
            page = max(1, int(q.get("page", 1))) if str(q.get("page", "1")).isdigit() else 1
            return Response({**meta, "columns": columns, "rows": rows[(page - 1) * size: page * size], "count": len(rows), "page": page, "page_size": size, "summary": summary})
        if fmt not in exports.CONTENT:
            raise serializers.ValidationError({"export": "Use csv, xlsx or pdf."})
        if len(rows) > exports.MAX_EXPORT_ROWS:
            raise serializers.ValidationError({"detail": f"This export exceeds {exports.MAX_EXPORT_ROWS} rows. Narrow the date range."})
        ctype, fn_export = exports.CONTENT[fmt]
        sub = f"{p.date_from} to {p.date_to}" + (f" · branch {p.branch}" if p.branch else "")
        body = fn_export(title, columns, rows, summary, sub) if fmt == "pdf" else fn_export(title, columns, rows, summary)
        audit.record("report.exported", actor=request.user, request=request, branch_id=p.branch, report=slug, format=fmt, rows=len(rows))  # exports leave the platform: always logged
        resp = HttpResponse(body, content_type=ctype)
        resp["Content-Disposition"] = f'attachment; filename="{slug}-{date.today().isoformat()}.{fmt}"'
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "private, no-store"
        return resp


class DashboardView(ReportBase):
    def get(self, request):
        u = request.user
        if u.is_platform_admin or not u.has_tenant_perm("report.view"):
            raise PermissionDenied("You are not allowed to view the dashboard.")
        p = self.params(request)
        return Response(dashboard.build(u, p))
