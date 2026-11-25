"""Transactional email. Content is passed to the Celery task by argument (never persisted); the task sends via Brevo
when BREVO_API_KEY is set, otherwise through Django's configured backend (console/locmem in dev)."""
import html
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction

from .models import EmailLog

log = logging.getLogger(__name__)
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _esc(s) -> str:
    return html.escape(str(s))


def _absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith("https://"):
        return url
    base = settings.FRONTEND_URL.rstrip("/")
    return base + url if url.startswith("/") and base.startswith("https://") else ""  # email clients need an absolute https URL


def _body(paragraphs, code, button, color) -> str:
    out = "".join(f'<p style="margin:0 0 14px;line-height:1.6;color:#334155">{_esc(p).replace(chr(10), "<br>")}</p>' for p in paragraphs)
    if code:
        out += (f'<p style="margin:18px 0;text-align:center"><span style="display:inline-block;background:#f1f5f9;border:1px dashed {color};border-radius:8px;'
                f'padding:12px 22px;font-size:26px;letter-spacing:6px;font-weight:bold;color:#0f172a">{_esc(code)}</span></p>')
    if button and button[1].startswith(("https://", "http://")):
        out += (f'<p style="margin:22px 0"><a href="{html.escape(button[1], quote=True)}" style="background:{color};color:#ffffff;padding:12px 22px;'
                f'border-radius:8px;text-decoration:none;display:inline-block;font-weight:bold">{_esc(button[0])}</a></p>')
    return out


def render_platform_html(*, title: str, paragraphs: list[str], button=None, code: str = "") -> str:
    """Template for emails sent by the platform itself (account, billing, backups, security). Uses the platform logo colours."""
    color, color2 = "#015dc9", "#25bcfb"
    logo = _absolute("/logo.webp")
    logo_html = f'<img src="{html.escape(logo, quote=True)}" width="36" height="36" alt="" style="vertical-align:middle;margin-right:10px;border-radius:6px;background:#fff">' if logo else ""
    contact = settings.PLATFORM_CONTACT_EMAIL
    return (f'<div style="background:#f1f5f9;padding:24px 12px;font-family:Arial,Helvetica,sans-serif">'
            f'<div style="max-width:580px;margin:auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">'
            f'<div style="background:{color};background-image:linear-gradient(135deg,{color},{color2});color:#fff;padding:20px 24px;font-size:20px;font-weight:bold">'
            f'{logo_html}{_esc(settings.PLATFORM_NAME)}</div>'
            f'<div style="padding:28px 24px"><h2 style="margin:0 0 16px;color:#0f172a;font-size:20px">{_esc(title)}</h2>{_body(paragraphs, code, button, color)}</div>'
            f'<div style="padding:16px 24px;background:#f8fafc;color:#64748b;font-size:12px;line-height:1.5">'
            f'You are receiving this email because of activity on your {_esc(settings.PLATFORM_NAME)} account.'
            f'{(" Questions? Contact " + _esc(contact) + ".") if contact else ""}</div></div></div>')


def render_pharmacy_html(*, pharmacy, title: str, paragraphs: list[str], button=None, code: str = "") -> str:
    """Template for emails sent in a pharmacy's name (receipts, order updates, staff mail): pharmacy logo, colour and contact details."""
    color = getattr(pharmacy, "primary_color", None) or "#015dc9"
    name = pharmacy.name
    logo = _absolute(pharmacy.logo.url) if getattr(pharmacy, "logo", None) else ""
    logo_html = f'<img src="{html.escape(logo, quote=True)}" height="36" alt="" style="vertical-align:middle;margin-right:10px;border-radius:6px;background:#fff;max-width:120px;object-fit:contain">' if logo else ""
    lines = [x for x in (pharmacy.address, pharmacy.contact_phone, pharmacy.contact_email) if x]
    contact = " &middot; ".join(_esc(x) for x in lines)
    return (f'<div style="background:#f1f5f9;padding:24px 12px;font-family:Arial,Helvetica,sans-serif">'
            f'<div style="max-width:580px;margin:auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">'
            f'<div style="background:{color};color:#fff;padding:20px 24px;font-size:20px;font-weight:bold">{logo_html}{_esc(name)}</div>'
            f'<div style="padding:28px 24px"><h2 style="margin:0 0 16px;color:#0f172a;font-size:20px">{_esc(title)}</h2>{_body(paragraphs, code, button, color)}</div>'
            f'<div style="padding:16px 24px;background:#f8fafc;color:#64748b;font-size:12px;line-height:1.6">'
            f'<strong style="color:#334155">{_esc(name)}</strong>{("<br>" + contact) if contact else ""}'
            f'<br><span style="color:#94a3b8">Sent securely via {_esc(settings.PLATFORM_NAME)}</span></div></div></div>')


def render_branded_html(*, title: str, paragraphs: list[str] = (), pharmacy=None, button: tuple[str, str] | None = None, code: str = "") -> str:
    """Picks the platform template (no pharmacy) or the pharmacy's own template. All dynamic text is escaped."""
    paragraphs = list(paragraphs)
    if pharmacy is None:
        return render_platform_html(title=title, paragraphs=paragraphs, button=button, code=code)
    return render_pharmacy_html(pharmacy=pharmacy, title=title, paragraphs=paragraphs, button=button, code=code)


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
