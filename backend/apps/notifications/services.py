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


FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _body(paragraphs, code, button, color) -> str:
    out = "".join(f'<p style="margin:0 0 16px;font-size:15px;line-height:1.7;color:#475569">{_esc(p).replace(chr(10), "<br>")}</p>' for p in paragraphs)
    if code:
        out += (f'<table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin:24px auto"><tr><td align="center" '
                f'style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:16px 28px">'
                f'<div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#94a3b8;margin-bottom:6px">Your code</div>'
                f'<div style="font-family:\'SFMono-Regular\',Consolas,Menlo,monospace;font-size:32px;letter-spacing:10px;font-weight:700;color:{color}">{_esc(code)}</div>'
                f'</td></tr></table>')
    if button and button[1].startswith(("https://", "http://")):
        out += (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0 8px"><tr><td align="center" bgcolor="{color}" '
                f'style="border-radius:12px"><a href="{html.escape(button[1], quote=True)}" style="display:inline-block;padding:14px 30px;font-size:15px;'
                f'font-weight:700;color:#ffffff;text-decoration:none;border-radius:12px">{_esc(button[0])} &nbsp;&rarr;</a></td></tr></table>'
                f'<p style="margin:12px 0 0;font-size:12px;color:#94a3b8;word-break:break-all">Button not working? Copy this link: '
                f'<a href="{html.escape(button[1], quote=True)}" style="color:{color}">{_esc(button[1])}</a></p>')
    return out


def _layout(*, brand: str, logo: str, color: str, color2: str, title: str, body: str, footer: str, preheader: str, eyebrow: str) -> str:
    logo_html = (f'<img src="{html.escape(logo, quote=True)}" height="40" alt="" style="display:block;height:40px;max-width:140px;border-radius:10px;background:#ffffff;padding:3px">' if logo else "")
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="color-scheme" content="light only"><title>{_esc(title)}</title></head>'
        f'<body style="margin:0;padding:0;background:#eef2f7;font-family:{FONT}">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">{_esc(preheader)}&#8199;&#847;&#8199;&#847;&#8199;&#847;</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#eef2f7"><tr><td align="center" style="padding:32px 14px">'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px">'
        # header
        f'<tr><td style="background:{color};background-image:linear-gradient(135deg,{color} 0%,{color2} 140%);border-radius:20px 20px 0 0;padding:28px 32px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{('<td width="1" style="padding-right:14px">' + logo_html + '</td>') if logo_html else ''}'
        f'<td style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:.2px">{_esc(brand)}</td></tr></table>'
        f'<div style="margin-top:22px;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,.75)">{_esc(eyebrow)}</div></td></tr>'
        # card
        f'<tr><td style="background:#ffffff;padding:36px 32px 32px;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0">'
        f'<h1 style="margin:0 0 18px;font-size:26px;line-height:1.25;font-weight:800;color:#0f172a;letter-spacing:-.3px">{_esc(title)}</h1>{body}</td></tr>'
        # accent rule + footer
        f'<tr><td style="height:4px;background:{color};background-image:linear-gradient(90deg,{color},{color2});font-size:0;line-height:0">&nbsp;</td></tr>'
        f'<tr><td style="background:#ffffff;border:1px solid #e2e8f0;border-top:0;border-radius:0 0 20px 20px;padding:24px 32px;font-size:12px;line-height:1.7;color:#64748b">{footer}</td></tr>'
        f'<tr><td align="center" style="padding:18px 8px;font-size:11px;color:#94a3b8">Please do not share links or codes from this email with anyone.</td></tr>'
        f'</table></td></tr></table></body></html>')


def render_platform_html(*, title: str, paragraphs: list[str], button=None, code: str = "", preheader: str = "") -> str:
    """Template for emails sent by the platform itself (account, billing, backups, security). Uses the platform logo colours."""
    contact = settings.PLATFORM_CONTACT_EMAIL
    footer = (f'<strong style="color:#334155">{_esc(settings.PLATFORM_NAME)}</strong><br>You are receiving this email because of activity on your account.'
              f'{("<br>Questions? Write to <a href=\'mailto:" + html.escape(contact, quote=True) + "\' style=\'color:#059669\'>" + _esc(contact) + "</a>.") if contact else ""}')
    return _layout(brand=settings.PLATFORM_NAME, logo=_absolute("/logo.webp"), color="#059669", color2="#142d3d", title=title, body=_body(paragraphs, code, button, "#059669"),
                   footer=footer, preheader=preheader or (paragraphs[0] if paragraphs else title), eyebrow="Account notification")


def render_pharmacy_html(*, pharmacy, title: str, paragraphs: list[str], button=None, code: str = "", preheader: str = "") -> str:
    """Template for emails sent in a pharmacy's name (receipts, order updates, staff mail): pharmacy logo, colours and contact details."""
    color = getattr(pharmacy, "primary_color", None) or "#015dc9"
    color2 = getattr(pharmacy, "secondary_color", None) or "#25bcfb"
    logo = _absolute(pharmacy.logo.url) if getattr(pharmacy, "logo", None) else ""
    lines = [x for x in (pharmacy.address, pharmacy.contact_phone, pharmacy.contact_email) if x]
    contact = "<br>".join(_esc(x) for x in lines)
    footer = (f'<strong style="color:#334155;font-size:13px">{_esc(pharmacy.name)}</strong>{("<br>" + contact) if contact else ""}'
              f'<br><span style="color:#94a3b8">Sent securely via {_esc(settings.PLATFORM_NAME)}</span>')
    return _layout(brand=pharmacy.name, logo=logo, color=color, color2=color2, title=title, body=_body(paragraphs, code, button, color),
                   footer=footer, preheader=preheader or (paragraphs[0] if paragraphs else title), eyebrow="Message from your pharmacy")


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
