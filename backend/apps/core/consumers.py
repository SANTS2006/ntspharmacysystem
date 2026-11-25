import asyncio
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .realtime import topic_group, user_group

TOPIC_PERMISSIONS = {"orders": "order.manage", "qr": "order.manage", "payments": "order.manage", "prescriptions": "prescription.view", "inventory": "inventory.view"}


@database_sync_to_async
def authenticate(raw):
    """Same checks as the REST authentication class; returns (user, groups, exp) or None."""
    from apps.accounts.models import User
    try:
        tok = AccessToken(raw)
        user = User.objects.select_related("tenant", "role").get(pk=tok["user_id"])
    except (TokenError, User.DoesNotExist, KeyError):
        return None
    if tok.get("cv") != user.credential_version or not user.is_active or user.must_change_password or user.is_platform_admin:
        return None
    if user.tenant is None or not user.tenant.is_active_tenant:
        return None
    groups = [user_group(user.tenant_id, user.pk)]
    if user.role.code != "customer":
        for topic, perm in TOPIC_PERMISSIONS.items():
            if user.has_tenant_perm(perm):
                groups.append(topic_group(user.tenant_id, topic, user.branch_id if user.is_branch_scoped else None))
    return user, groups, int(tok["exp"])


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Authenticate with a first message {"type":"auth","token":"<access JWT>"} (tokens never travel in the URL).
    Subscriptions are derived server-side from the user's tenant, branch and permissions; the client cannot choose groups."""
    AUTH_TIMEOUT = 10

    async def connect(self):
        self.exp, self.authed = 0, False
        await self.accept()
        self._timer = asyncio.get_event_loop().call_later(self.AUTH_TIMEOUT, lambda: asyncio.ensure_future(self._expire_unauthenticated()))

    async def _expire_unauthenticated(self):
        if not self.authed:
            await self.close(code=4401)

    async def receive_json(self, content, **kw):
        if self.authed or content.get("type") != "auth":
            return
        res = await authenticate(str(content.get("token", "")))
        if res is None:
            await self.close(code=4401)
            return
        user, groups, self.exp = res
        for g in groups:
            await self.channel_layer.group_add(g, self.channel_name)
        self.groups_joined, self.authed = groups, True
        await self.send_json({"type": "ready"})

    async def push(self, message):
        if not self.authed:
            return
        if time.time() >= self.exp:  # token lifetime ends the subscription; the client reconnects with a fresh token
            await self.close(code=4401)
            return
        await self.send_json({"type": "event", "event": message["event"], "data": message["data"]})

    async def disconnect(self, code):
        for g in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(g, self.channel_name)
