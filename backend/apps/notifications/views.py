from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAuthenticatedAndSettled
from apps.core.views import TenantContextMixin

from .models import Notification


def out(n: Notification) -> dict:
    return {"id": n.pk, "kind": n.kind, "level": n.level, "title": n.title, "body": n.body, "link": n.link, "read": n.read_at is not None,
            "read_at": n.read_at, "created_at": n.created_at}


class Base(TenantContextMixin, APIView):
    """Every signed-in account (platform, staff, customer) sees only its own notifications."""
    permission_classes = [IsAuthenticatedAndSettled]

    def mine(self):
        return Notification.objects.filter(user=self.request.user)


class ListView(Base):
    def get(self, request):
        qs = self.mine()
        if request.query_params.get("unread") == "1":
            qs = qs.filter(read_at__isnull=True)
        if kind := request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        pg = PageNumberPagination()
        size = request.query_params.get("page_size", "")
        pg.page_size = max(1, min(int(size), 50)) if size.isdigit() else 15
        resp = pg.get_paginated_response([out(n) for n in pg.paginate_queryset(qs, request)])
        resp.data["unread"] = self.mine().filter(read_at__isnull=True).count()
        return resp


class DetailView(Base):
    def get(self, request, pk):
        return Response(out(get_object_or_404(self.mine(), pk=pk)))

    def delete(self, request, pk):
        get_object_or_404(self.mine(), pk=pk).delete()
        return Response(status=204)


class ReadView(Base):
    def post(self, request, pk):
        n = get_object_or_404(self.mine(), pk=pk)
        read = request.data.get("read", True) is not False
        n.read_at = (n.read_at or timezone.now()) if read else None
        n.save(update_fields=["read_at"])
        return Response(out(n))


class ReadAllView(Base):
    def post(self, request):
        return Response({"updated": self.mine().filter(read_at__isnull=True).update(read_at=timezone.now())})
