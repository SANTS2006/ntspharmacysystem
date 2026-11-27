"""Search engines and link previews often do not run JavaScript, so public pages get their title, description, canonical address and
social tags written into index.html on the server. robots.txt and sitemap.xml list only public pages."""
import html
import re

from django.conf import settings
from django.http import HttpResponse

MARKETING = {
    "": ("{p} | Pharmacy Management Platform", "{p} helps pharmacies run inventory, prescriptions, point of sale, online orders, mobile money payments and accounting across every branch."),
    "features": ("Features | {p}", "Inventory with batch and expiry tracking, pharmacist-approved prescriptions, POS, online ordering and finance in one platform."),
    "solutions": ("Solutions | {p}", "For independent pharmacies, multi-branch chains, hospital pharmacies and wholesalers."),
    "pricing": ("Pricing | {p}", "Simple subscription plans for pharmacies of every size."),
    "about": ("About | {p}", "Why we built a pharmacy platform for safe dispensing and clear business records."),
    "faq": ("Frequently asked questions | {p}", "Answers about setup, security, branches, payments and support."),
    "contact": ("Contact | {p}", "Talk to our team about registering your pharmacy."),
    "support": ("Support | {p}", "Get help with your pharmacy account."),
}
SITE_PAGES = {"": "Online pharmacy", "about": "About us", "contact": "Contact us", "products": "Medicines and health products", "services": "Pharmacy services", "institutional": "Bulk and institutional orders"}


LEGAL = "privacy|terms|payment-refund|data-protection|security|cookies"
SYSTEM_ROUTES = re.compile(
    rf"^(?:|features|solutions|pricing|about|faq|contact|support|legal/(?:{LEGAL})|reset-password|accept-invitation|change-password|dashboard"
    r"|platform/(?:login|forgot-password)|platform(?:/(?:dashboard|pharmacies(?:/\d+)?|billing|audit|backups|website|website-contact|settings|notifications(?:/\d+)?))?)$")
# Mirrors frontend/src/App.tsx: add new pharmacy pages here too, or they are served with status 404.
PHARMACY_ROUTES = re.compile(
    r"^(?:|about|contact|products|checkout|services|institutional|feedback|orders(?:/\d+)?|menu/[^/]+|login|register|verify|forgot-password"
    r"|admin(?:/(?:login|forgot-password|dashboard|overview|branches|staff|roles|medicines|inventory|procurement|prescriptions(?:/\d+)?|pos"
    r"|orders(?:/\d+)?|payments|accounting|hr|payroll|my-work|reports|engagement|deliveries|customers(?:/\d+)?|pharmacy-settings|subscription|website|website-contact"
    r"|settings|notifications(?:/\d+)?))?"
    r"|account(?:/(?:dashboard|orders(?:/\d+)?|payments|care|settings|notifications(?:/\d+)?))?)$")


def is_known_route(path: str) -> bool:
    clean = path.strip("/")
    if SYSTEM_ROUTES.match(clean):
        return True
    from apps.tenants.models import RESERVED_SLUGS, Pharmacy
    slug, _, rest = clean.partition("/")
    if slug in RESERVED_SLUGS or not PHARMACY_ROUTES.match(rest):
        return False
    return Pharmacy.objects.filter(slug=slug, status=Pharmacy.Status.ACTIVE).exists()


def base_url(request) -> str:
    configured = (settings.FRONTEND_URL or "").rstrip("/")
    return configured if configured.startswith("https://") else f"{request.scheme}://{request.get_host()}"


def page_meta(path: str):
    """-> (title, description, image, indexable) for a public path, or None for private/unknown pages."""
    parts = [p for p in path.strip("/").split("/") if p]
    first = parts[0] if parts else ""
    platform = settings.PLATFORM_NAME
    if len(parts) <= 1 and first in MARKETING:
        title, desc = MARKETING[first]
        return title.format(p=platform), desc.format(p=platform), "/logo.webp", True
    from apps.tenants.models import RESERVED_SLUGS, Pharmacy
    if not first or first in RESERVED_SLUGS:
        return None
    page = parts[1] if len(parts) > 1 else ""
    if len(parts) > 2 or page not in SITE_PAGES:
        return None
    t = Pharmacy.objects.filter(slug=first, status=Pharmacy.Status.ACTIVE).first()
    if t is None:
        return None
    place = ", ".join(x for x in (t.city, t.country) if x)
    desc = (t.description or f"{t.name} is a pharmacy in {place}. Browse medicines, book services and order online.").replace("\n", " ")[:160]
    return f"{t.name} | {SITE_PAGES[page]}", desc, t.logo.url if t.logo else "/logo.webp", True


def inject(index_html: str, request) -> str:
    meta = page_meta(request.path)
    if meta is None:  # signed-in areas and unknown pages must never be indexed
        return index_html.replace("</head>", '<meta name="robots" content="noindex,nofollow"></head>', 1)
    title, desc, image, _ = meta
    base = base_url(request)
    url = base + (request.path.rstrip("/") or "/")
    image = image if image.startswith("https://") else base + image
    e = lambda v: html.escape(v, quote=True)  # noqa: E731
    out = re.sub(r"<title>.*?</title>", lambda _: f"<title>{e(title)}</title>", index_html, count=1, flags=re.S)
    out = re.sub(r'<meta name="description"[^>]*>', lambda _: f'<meta name="description" content="{e(desc)}" />', out, count=1)
    tags = (f'<link rel="canonical" href="{e(url)}"><meta property="og:type" content="website"><meta property="og:title" content="{e(title)}">'
            f'<meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(url)}"><meta property="og:image" content="{e(image)}">'
            f'<meta name="twitter:card" content="summary"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}">')
    return out.replace("</head>", tags + "</head>", 1)


def robots_txt(request):
    body = ("User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /platform\nDisallow: /*/admin\nDisallow: /*/account\nDisallow: /*/login\n"
            "Disallow: /*/checkout\nDisallow: /reset-password\nDisallow: /accept-invitation\n"
            f"Sitemap: {base_url(request)}/sitemap.xml\n")
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    from apps.tenants.models import Pharmacy
    base = base_url(request)
    urls = [f"{base}/{p}" for p in MARKETING]
    for slug in Pharmacy.objects.filter(status=Pharmacy.Status.ACTIVE).values_list("slug", flat=True)[:5000]:
        urls += [f"{base}/{slug}" + (f"/{p}" if p else "") for p in SITE_PAGES]
    items = "".join(f"<url><loc>{html.escape(u)}</loc></url>" for u in urls)
    return HttpResponse(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>',
                        content_type="application/xml; charset=utf-8")
