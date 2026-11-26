"""Monime gateway client and webhook signature verification.

Checked against Monime's OpenAPI document (release caph.2025-08-23): checkout sessions, payment codes, the `monime-signature` webhook header
(`t=<unix>,v1=<base64 HMAC-SHA256 of "<t>_<raw body>">`) and the required Space-Id / Idempotency-Key headers. Amounts are in minor units.
One Monime space serves the whole platform; credentials come only from the environment and are never stored or returned by any API."""
import base64
import binascii
import hashlib
import hmac
import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from rest_framework.exceptions import APIException

SIGNATURE_TOLERANCE_PAST = 300   # seconds a signature stays valid
SIGNATURE_TOLERANCE_FUTURE = 60  # clock-skew allowance
API_VERSION = "caph.2025-08-23"
CURRENCIES = ("SLE", "USD")


class ProviderError(APIException):
    status_code = 502
    default_code = "provider_error"
    default_detail = "The payment provider could not be reached. Please try again."


@dataclass(frozen=True)
class Cfg:
    space_id: str
    access_token: str
    webhook_secret: str

    @property
    def ready(self) -> bool:
        return bool(self.space_id and self.access_token)


def config() -> Cfg:
    return Cfg(settings.MONIME_SPACE_ID, settings.MONIME_ACCESS_TOKEN, settings.MONIME_WEBHOOK_SECRET)


def ready() -> bool:
    return config().ready


def to_minor(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).to_integral_value())


def idempotency_key(scope, reference: str) -> str:
    """Unique across the whole platform (payment numbers repeat between pharmacies, and they all share one Monime space). Max 64 chars."""
    raw = f"nts-{scope}-{reference}"
    return raw if len(raw) <= 64 else "nts-" + hashlib.sha256(raw.encode()).hexdigest()[:60]


def _context():
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


def _request(method: str, path: str, body: dict | None = None, idem: str | None = None) -> dict:
    cfg = config()
    if not cfg.ready:
        raise ProviderError("Mobile money payments are not configured.")
    headers = {"Authorization": f"Bearer {cfg.access_token}", "Monime-Space-Id": cfg.space_id, "Monime-Version": API_VERSION,
               "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "NTS-Pharmacy/1.0"}
    if idem:
        headers["Idempotency-Key"] = idem
    req = urllib.request.Request(settings.MONIME_API_BASE.rstrip("/") + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=20, context=_context()) as r:  # noqa: S310 (https host from settings)
            payload = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        reason = ""
        try:
            err = json.loads(e.read() or b"{}")
            reason = str((err.get("error") or {}).get("message") or "")[:200]
        except (ValueError, AttributeError):
            pass
        raise ProviderError(f"The payment provider rejected the request ({e.code}){': ' + reason if reason else '.'}")
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise ProviderError()
    if method == "DELETE":
        return {}
    if payload.get("success") is False or "result" not in payload:
        raise ProviderError("The payment provider returned an unexpected response.")
    return payload["result"]


def create_checkout_session(*, key: str, reference: str, name: str, amount_minor: int, currency: str, success_url: str, cancel_url: str) -> dict:
    return _request("POST", "/v1/checkout-sessions", {
        "name": name[:150], "reference": reference[:255], "successUrl": success_url[:255], "cancelUrl": cancel_url[:255],
        "lineItems": [{"type": "custom", "name": name[:100], "quantity": 1, "price": {"currency": currency, "value": amount_minor}}],
        "metadata": {"payment_reference": reference[:100]},
    }, idem=key)


def retrieve_checkout_session(session_id: str) -> dict:
    return _request("GET", f"/v1/checkout-sessions/{session_id}")


def create_payment_code(*, key: str, reference: str, name: str, amount_minor: int, currency: str, duration: str = "10m", customer_name: str = "") -> dict:
    """A one-time USSD code the customer dials to pay at the counter."""
    body = {"name": (name if len(name) >= 3 else f"Pay {name}")[:64], "mode": "one_time", "enable": True, "duration": duration,
            "amount": {"currency": currency, "value": amount_minor}, "reference": reference[:64], "metadata": {"payment_reference": reference[:100]}}
    if customer_name:
        body["customer"] = {"name": customer_name[:100]}
    return _request("POST", "/v1/payment-codes", body, idem=key)


def retrieve_payment_code(code_id: str) -> dict:
    return _request("GET", f"/v1/payment-codes/{code_id}")


def delete_payment_code(code_id: str) -> None:
    _request("DELETE", f"/v1/payment-codes/{code_id}")


def check_credentials() -> dict:
    """Read-only call that fails unless both the token and the space id are accepted."""
    return _request("GET", "/v1/payment-codes?limit=1")


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
