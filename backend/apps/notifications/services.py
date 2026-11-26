"""Transactional email. Content is passed to the Celery task by argument (never persisted); the task sends via Brevo
when BREVO_API_KEY is set, otherwise through Django's configured backend (console/locmem in dev)."""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction

from . import templates_html
from .models import EmailLog

log = logging.getLogger(__name__)
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


# Subject keywords decide the small label above the heading, so every email states what it is about.
EYEBROWS = (("receipt", "Receipt"), ("payment", "Payment"), ("refund", "Refund"), ("order", "Order update"), ("password", "Account security"),
            ("verif", "Email verification"), ("email", "Account security"), ("appointment", "Appointment"), ("salary", "Payroll"), ("stock", "Stock alert"),
            ("backup", "System alert"), ("restore", "System alert"), ("welcome", "Welcome"), ("account", "Your account"), ("code", "Verification"))


def _eyebrow(title: str, fallback: str) -> str:
    low = title.lower()
    return next((label for key, label in EYEBROWS if key in low), fallback)


def render_branded_html(*, title: str, paragraphs: list[str] = (), pharmacy=None, button: tuple[str, str] | None = None, code: str = "",
                        details: list[tuple[str, str]] | None = None, items: dict | None = None) -> str:
    """Picks the platform template (no pharmacy) or the pharmacy's own template. All dynamic text is escaped."""
    kw = dict(title=title, paragraphs=list(paragraphs), button=button, code=code, details=details, items=items)
    if pharmacy is None:
        return templates_html.render_platform_html(eyebrow=_eyebrow(title, "Account notification"), **kw)
    return templates_html.render_pharmacy_html(pharmacy=pharmacy, eyebrow=_eyebrow(title, "From your pharmacy"), **kw)


def receipt_parts(data: dict) -> dict:
    """Receipt snapshot -> the tables used in receipt emails."""
    cur = data.get("currency", "")
    totals = [("Subtotal", f"{cur} {data['subtotal']}"), ("Tax", f"{cur} {data.get('tax_total', '0.00')}")]
    if str(data.get("discount_total", "0.00")) not in ("0", "0.00"):
        totals.append(("Discount", f"-{cur} {data['discount_total']}"))
    if str(data.get("delivery_fee", "0.00")) not in ("0", "0.00"):
        totals.append(("Delivery fee", f"{cur} {data['delivery_fee']}"))
    totals.append(("Total", f"{cur} {data['total']}"))
    return {"items": {"columns": ["Item", "Qty", "Amount"], "rows": [[l["name"], l["quantity"], l["total"]] for l in data["lines"]], "totals": totals},
            "details": [("Receipt number", data.get("receipt_number", "")), ("Reference", data.get("order_reference") or data.get("sale_reference", "")),
                        ("Branch", data.get("branch", "")), ("Paid", f"{cur} {data.get('amount_paid', '')}"), ("Status", data.get("payment_status", ""))]}


def send_email(*, to: str, subject: str, text: str, html_body: str = "", tenant=None, template: str = "") -> EmailLog:
    """Queue an email. Safe to call inside transactions: dispatch happens on commit and never raises to the caller."""
    if not html_body:  # every email gets a branded template: the pharmacy's own, or the platform's
        html_body = render_branded_html(title=subject, paragraphs=text.split("\n\n"), pharmacy=tenant)
    entry = EmailLog.objects.create(tenant=tenant, to_email=to, subject=subject[:255], template=template)
    from .tasks import deliver_email
    transaction.on_commit(lambda: deliver_email.delay(entry.pk, text, html_body))
    return entry


def _post_brevo(payload: dict) -> str:
    req = urllib.request.Request(
        BREVO_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"api-key": settings.BREVO_API_KEY, "content-type": "application/json", "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed https URL)
            return json.loads(resp.read() or b"{}").get("messageId", "")
    except urllib.error.HTTPError as e:  # keep Brevo's reason (e.g. unverified sender) for the EmailLog; the API key is never included
        raise RuntimeError(f"Brevo HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None


def deliver(entry: EmailLog, text: str, html_body: str) -> None:
    entry.attempts += 1
    try:
        if settings.BREVO_API_KEY:
            entry.provider = "brevo"
            t = entry.tenant
            payload = {
                "sender": {"name": t.name if t else settings.PLATFORM_NAME, "email": settings.DEFAULT_FROM_EMAIL},  # sender address must be verified in Brevo
                "to": [{"email": entry.to_email}], "subject": entry.subject,
                "textContent": text, **({"htmlContent": html_body} if html_body else {})}
            if t and t.contact_email:
                payload["replyTo"] = {"email": t.contact_email, "name": t.name}
            entry.provider_message_id = _post_brevo(payload)[:120]
        else:
            entry.provider = "django"
            msg = EmailMultiAlternatives(entry.subject, text, settings.DEFAULT_FROM_EMAIL, [entry.to_email])
            if html_body:
                msg.attach_alternative(html_body, "text/html")
            msg.send()
        entry.status, entry.last_error = EmailLog.Status.SENT, ""
    except Exception as exc:  # recorded; retried by the task
        entry.status, entry.last_error = EmailLog.Status.FAILED, f"{type(exc).__name__}: {exc}"[:500]
        entry.save()
        raise
    entry.save()
