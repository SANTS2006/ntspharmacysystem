"""Monime gateway client and webhook signature verification.

Source: Monime developer docs (docs.monime.io): checkout sessions (POST /v1/checkout-sessions, GET /v1/checkout-sessions/{id}), headers
Authorization/Monime-Space-Id/Idempotency-Key, and webhooks signed with `Monime-Signature: t=<unix>,v1=<base64 HMAC-SHA256 of "<t>_<raw body>">`.
These details were read from documentation summaries and have NOT been exercised against Monime with real credentials. Re-check the line item schema,
minor-unit rule and the exact session id prefixes against https://docs.monime.io/apis/openapi/caph-2025-08-23.json before going live."""
import base64
import binascii
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from django.conf import settings
from rest_framework.exceptions import APIException

SIGNATURE_TOLERANCE_PAST = 300   # seconds a signature stays valid
SIGNATURE_TOLERANCE_FUTURE = 60  # clock-skew allowance


class ProviderError(APIException):
    status_code = 502
    default_code = "provider_error"
    default_detail = "The payment provider could not be reached. Please try again."


def _request(cfg, method: str, path: str, body: dict | None = None, idempotency_key: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {cfg.access_token}", "Monime-Space-Id": cfg.space_id, "Accept": "application/json", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    req = urllib.request.Request(settings.MONIME_API_BASE.rstrip("/") + path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (https host from settings)
            payload = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise ProviderError(f"The payment provider rejected the request ({e.code}).")
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise ProviderError()
    if payload.get("success") is False or "result" not in payload:
        raise ProviderError("The payment provider returned an unexpected response.")
    return payload["result"]


def create_checkout_session(cfg, *, reference: str, name: str, amount_minor: int, currency: str, success_url: str, cancel_url: str) -> dict:
    return _request(cfg, "POST", "/v1/checkout-sessions", {
        "name": name[:150], "reference": reference, "successUrl": success_url[:255], "cancelUrl": cancel_url[:255],
        "lineItems": [{"type": "custom", "name": name[:150], "quantity": 1, "price": {"currency": currency, "value": amount_minor}}],
        "metadata": {"payment_reference": reference},
    }, idempotency_key=reference)


def retrieve_checkout_session(cfg, session_id: str) -> dict:
    return _request(cfg, "GET", f"/v1/checkout-sessions/{session_id}")


def verify_signature(secret: str, header: str, raw_body: bytes, now: float | None = None) -> bool:
    """HMAC-SHA256 over b"<t>_" + raw body, base64 compared in constant time, with replay-window checks. `raw_body` must be the unparsed request body."""
    if not secret or not header:
        return False
    parts = {}
    for chunk in header.split(","):
        k, _, v = chunk.strip().partition("=")
        parts[k] = v
    try:
        t = int(parts["t"])
        given = base64.b64decode(parts["v1"], validate=True)
    except (KeyError, ValueError, binascii.Error):
        return False
    now = time.time() if now is None else now
    if now - t > SIGNATURE_TOLERANCE_PAST or t - now > SIGNATURE_TOLERANCE_FUTURE:
        return False
    expected = hmac.new(secret.encode(), f"{t}_".encode() + raw_body, hashlib.sha256).digest()
    return hmac.compare_digest(expected, given)
