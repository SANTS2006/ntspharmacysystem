"""Email HTML. Table layout with inline styles so it renders in Gmail, Outlook and phone clients. Every dynamic value is escaped."""
import html

from django.conf import settings

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
INK, MUTED, LINE, SOFT, CANVAS = "#0f172a", "#64748b", "#e2e8f0", "#f8fafc", "#eef2f6"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def absolute(url: str) -> str:
    """Email clients need an absolute https URL; WebP is swapped for PNG because several clients cannot show it."""
    if not url:
        return ""
    if not url.startswith("https://"):
        base = settings.FRONTEND_URL.rstrip("/")
        if not (url.startswith("/") and base.startswith("https://")):
            return ""
        url = base + url
    if "res.cloudinary.com" in url and url.lower().endswith(".webp"):
        url = url[:-5] + ".png"
    return url


def _rgb(color: str):
    try:
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return (5, 150, 105)


def on_color(color: str) -> str:
    """White or dark text, whichever stays readable on the pharmacy's own colour."""
    r, g, b = _rgb(color)
    return INK if (0.299 * r + 0.587 * g + 0.114 * b) > 165 else "#ffffff"


def tint(color: str, amount: float = 0.92) -> str:
    return "#" + "".join(f"{round(c + (255 - c) * amount):02x}" for c in _rgb(color))


def _paragraphs(paragraphs):
    return "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.75;color:#334155">{esc(p).replace(chr(10), "<br>")}</p>' for p in paragraphs)


def _code(code, color):
    boxes = "".join(f'<td style="padding:0 3px"><div style="width:42px;height:52px;line-height:52px;text-align:center;background:#ffffff;border:1px solid {LINE};'
                    f'border-bottom:3px solid {color};border-radius:10px;font-family:Consolas,Menlo,monospace;font-size:26px;font-weight:700;color:{INK}">{esc(c)}</div></td>'
                    for c in str(code))
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:22px 0"><tr><td align="center" style="background:{tint(color)};border-radius:16px;padding:20px 8px">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{MUTED};margin-bottom:12px">Your code</div>'
            f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>{boxes}</tr></table>'
            f'<div style="margin-top:10px;font-family:Consolas,Menlo,monospace;font-size:13px;color:{MUTED}">{esc(code)}</div></td></tr></table>')


def _details(details, color):
    rows = "".join(f'<tr><td style="padding:11px 16px;font-size:13px;color:{MUTED};border-top:{"0" if i == 0 else "1px solid " + LINE}">{esc(k)}</td>'
                   f'<td align="right" style="padding:11px 16px;font-size:14px;font-weight:600;color:{INK};border-top:{"0" if i == 0 else "1px solid " + LINE};word-break:break-word">{esc(v)}</td></tr>'
                   for i, (k, v) in enumerate(details))
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;background:{SOFT};border:1px solid {LINE};'
            f'border-left:4px solid {color};border-radius:12px">{rows}</table>')


def _items(table, color):
    cols, rows, totals = table["columns"], table["rows"], table.get("totals", [])
    align = lambda i: "left" if i == 0 else "right"  # noqa: E731
    head = "".join(f'<th align="{align(i)}" style="padding:10px 12px;font-size:11px;letter-spacing:1px;text-transform:uppercase;color:{on_color(color)};background:{color}">{esc(c)}</th>'
                   for i, c in enumerate(cols))
    body = "".join("<tr>" + "".join(f'<td align="{align(i)}" style="padding:11px 12px;font-size:14px;color:{INK};border-bottom:1px solid {LINE}">{esc(v)}</td>'
                                    for i, v in enumerate(r)) + "</tr>" for r in rows)
    foot = "".join(f'<tr><td colspan="{len(cols) - 1}" align="right" style="padding:8px 12px;font-size:{15 if strong else 13}px;font-weight:{800 if strong else 400};color:{INK if strong else MUTED}">{esc(k)}</td>'
                   f'<td align="right" style="padding:8px 12px;font-size:{17 if strong else 13}px;font-weight:{800 if strong else 600};color:{INK}">{esc(v)}</td></tr>'
                   for k, v, strong in [(t[0], t[1], i == len(totals) - 1) for i, t in enumerate(totals)])
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;border:1px solid {LINE};border-radius:12px;overflow:hidden">'
            f'<tr>{head}</tr>{body}{foot}</table>')


def _button(button, color):
    label, url = button
    if not url.startswith(("https://", "http://")):
        return ""
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:26px auto 10px"><tr><td align="center" bgcolor="{color}" style="border-radius:999px">'
            f'<a href="{esc(url)}" style="display:inline-block;padding:15px 36px;font-size:15px;font-weight:700;color:{on_color(color)};text-decoration:none;border-radius:999px">{esc(label)}&nbsp;&nbsp;&rarr;</a></td></tr></table>'
            f'<p style="margin:10px 0 0;text-align:center;font-size:12px;line-height:1.6;color:#94a3b8;word-break:break-all">Button not working? Copy this link:<br><a href="{esc(url)}" style="color:{MUTED}">{esc(url)}</a></p>')


def body_html(*, paragraphs, color, code="", details=None, items=None, button=None) -> str:
    out = _paragraphs(paragraphs)
    if code:
        out += _code(code, color)
    if details:
        out += _details(details, color)
    if items:
        out += _items(items, color)
    if button:
        out += _button(button, color)
    return out


def layout(*, brand, tagline, logo, color, color2, title, eyebrow, body, preheader, contacts, website, small_print) -> str:
    fg = on_color(color)
    initial = esc((brand or "N")[0].upper())
    mark = (f'<img src="{esc(logo)}" width="56" height="56" alt="{esc(brand)}" style="display:block;width:56px;height:56px;object-fit:contain;border-radius:14px;background:#ffffff;padding:4px">'
            if logo else f'<div style="width:64px;height:64px;line-height:64px;text-align:center;border-radius:16px;background:#ffffff;color:{color if on_color(color) == "#ffffff" else INK};font-size:28px;font-weight:800">{initial}</div>')
    contact_cells = "".join(f'<tr><td style="padding:3px 0;font-size:12px;color:{MUTED};width:86px;vertical-align:top">{esc(k)}</td><td style="padding:3px 0;font-size:13px;color:#334155">{esc(v)}</td></tr>'
                            for k, v in contacts if v)
    site = (f'<a href="{esc(website)}" style="display:inline-block;margin-top:14px;padding:9px 18px;border:1px solid {LINE};border-radius:999px;font-size:13px;font-weight:700;color:{INK};text-decoration:none">Visit our website</a>'
            if website.startswith("https://") else "")
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><title>{esc(title)}</title></head>'
        f'<body style="margin:0;padding:0;background:{CANVAS};font-family:{FONT}">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">{esc(preheader)}&#8199;&#847;&#8199;&#847;&#8199;&#847;</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{CANVAS}"><tr><td align="center" style="padding:28px 12px">'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px">'
        # brand header
        f'<tr><td align="center" bgcolor="{color}" style="background:{color};background-image:linear-gradient(135deg,{color},{color2});border-radius:24px 24px 0 0;padding:32px 28px 56px">'
        f'<table role="presentation" cellpadding="0" cellspacing="0"><tr><td align="center">{mark}</td></tr></table>'
        f'<div style="margin-top:14px;font-size:21px;font-weight:800;color:{fg};letter-spacing:-.2px">{esc(brand)}</div>'
        f'<div style="margin-top:4px;font-size:13px;color:{fg};opacity:.85">{esc(tagline)}</div></td></tr>'
        # floating card
        f'<tr><td style="padding:0 18px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:-30px;background:#ffffff;border:1px solid {LINE};border-radius:20px;box-shadow:0 10px 30px rgba(15,23,42,.08)">'
        f'<tr><td style="padding:32px 30px">'
        f'<span style="display:inline-block;padding:5px 12px;border-radius:999px;background:{tint(color)};font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:{INK}">{esc(eyebrow)}</span>'
        f'<h1 style="margin:14px 0 18px;font-size:25px;line-height:1.3;font-weight:800;color:{INK};letter-spacing:-.4px">{esc(title)}</h1>{body}</td></tr></table></td></tr>'
        # contact footer
        f'<tr><td style="padding:22px 18px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid {LINE};border-radius:16px"><tr><td style="padding:22px 26px">'
        f'<div style="font-size:14px;font-weight:800;color:{INK};margin-bottom:8px">{esc(brand)}</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0">{contact_cells}</table>{site}</td></tr></table></td></tr>'
        f'<tr><td align="center" style="padding:18px 24px;font-size:11px;line-height:1.7;color:#94a3b8">{esc(small_print)}<br>Never share passwords, codes or links from this email.</td></tr>'
        f'</table></td></tr></table></body></html>')


def render_platform_html(*, title, paragraphs, button=None, code="", details=None, items=None, preheader="", eyebrow="Account notification") -> str:
    color, color2 = "#059669", "#142d3d"
    return layout(brand=settings.PLATFORM_NAME, tagline="Pharmacy management, made simple", logo=absolute("/favicon.png"), color=color, color2=color2,
                  title=title, eyebrow=eyebrow, preheader=preheader or (paragraphs[0] if paragraphs else title),
                  body=body_html(paragraphs=paragraphs, color=color, code=code, details=details, items=items, button=button),
                  contacts=[("Support", settings.PLATFORM_CONTACT_EMAIL), ("WhatsApp", settings.PLATFORM_WHATSAPP_NUMBER)],
                  website=absolute("/"), small_print="You are receiving this email because of activity on your account.")


def render_pharmacy_html(*, pharmacy, title, paragraphs, button=None, code="", details=None, items=None, preheader="", eyebrow="From your pharmacy") -> str:
    color = getattr(pharmacy, "primary_color", None) or "#015dc9"
    color2 = getattr(pharmacy, "secondary_color", None) or "#25bcfb"
    logo = absolute(pharmacy.logo.url) if getattr(pharmacy, "logo", None) else ""
    place = ", ".join(x for x in (pharmacy.address, getattr(pharmacy, "city", ""), getattr(pharmacy, "country", "")) if x)
    tagline = (getattr(pharmacy, "description", "") or "").strip().split("\n")[0]
    tagline = tagline[:87].rstrip() + "…" if len(tagline) > 90 else tagline or "Your trusted pharmacy"
    from apps.core.links import site_url
    return layout(brand=pharmacy.name, tagline=tagline, logo=logo, color=color, color2=color2, title=title, eyebrow=eyebrow,
                  preheader=preheader or (paragraphs[0] if paragraphs else title),
                  body=body_html(paragraphs=paragraphs, color=color, code=code, details=details, items=items, button=button),
                  contacts=[("Address", place), ("Phone", pharmacy.contact_phone), ("Email", pharmacy.contact_email),
                            ("Licence", getattr(pharmacy, "license_number", "")), ("Registration", getattr(pharmacy, "registration_number", ""))],
                  website=absolute(site_url(pharmacy.slug)), small_print=f"Sent securely by {pharmacy.name} through {settings.PLATFORM_NAME}.")
