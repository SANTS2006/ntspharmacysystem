"""Real-time fan-out through Channels. Payloads carry ONLY ids/status/reference (never patient or customer data):
clients refetch details through the normal, permission-checked REST API."""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

log = logging.getLogger(__name__)
TOPICS = ("orders", "qr", "prescriptions", "inventory", "payments")


def user_group(tenant_id, user_id) -> str:
    return f"t{tenant_id}.u{user_id}"


def topic_group(tenant_id, topic, branch_id=None) -> str:
    return f"t{tenant_id}.b{branch_id}.{topic}" if branch_id else f"t{tenant_id}.all.{topic}"


def notify(groups, event: str, data: dict) -> None:
    """Sent after the surrounding transaction commits, and never raises into business code."""
    groups = [g for g in groups if g]

    def send():
        try:
            layer = get_channel_layer()
            if layer is None:
                return
            for g in groups:
                async_to_sync(layer.group_send)(g, {"type": "push", "event": event, "data": data})
        except Exception:  # real-time is best effort; REST polling remains the fallback
            log.exception("realtime notify failed for %s", event)

    transaction.on_commit(send)


def notify_topic(tenant_id, branch_id, topic, event, data, users=()):
    notify([topic_group(tenant_id, topic, branch_id), topic_group(tenant_id, topic)] + [user_group(tenant_id, u) for u in users if u], event, data)
