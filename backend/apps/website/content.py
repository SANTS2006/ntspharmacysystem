"""The only shapes website content may take. Anything unknown is dropped, text is length-limited and links must be safe, so an editor
(or a stolen editor session) cannot inject markup or script into a public page: the browser renders these values as plain text."""
from rest_framework.exceptions import ValidationError

MODELS = {"none", "pharmacy", "capsules", "molecule", "dna", "cross"}
BLOCKS = {"text", "items", "split", "gallery", "stats", "cta", "branches", "products", "services", "plans", "contact", "map"}
LAYOUTS = {"cards", "accordion", "carousel", "steps", "list"}
ANIMATIONS = {"none", "up", "left", "right", "zoom"}
BACKGROUNDS = {"plain", "tinted", "brand"}
MAX_BLOCKS, MAX_ITEMS = 30, 24


def text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ""


def link(value):
    """Site paths, anchors, https, mail and phone links only. Never javascript:, data: or protocol-relative addresses."""
    v = text(value, 500)
    if v.startswith(("https://", "mailto:", "tel:", "#")) or (v.startswith("/") and not v.startswith("//") and "\\" not in v):
        return v
    return ""


def image(value):
    v = link(value)
    return v if v.startswith(("https://", "/")) else ""


def choice(value, allowed, default):
    return value if isinstance(value, str) and value in allowed else default


def button(value):
    value = value if isinstance(value, dict) else {}
    return {"label": text(value.get("label"), 60), "href": link(value.get("href"))}


def _dicts(value, limit):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit or not all(isinstance(v, dict) for v in value):
        raise ValidationError({"content": f"Lists may hold at most {limit} entries."})
    return value


def clean_page(data):
    if not isinstance(data, dict):
        raise ValidationError({"content": "Content must be an object."})
    hero = data.get("hero") if isinstance(data.get("hero"), dict) else {}
    out = {"hero": {"eyebrow": text(hero.get("eyebrow"), 80), "title": text(hero.get("title"), 160), "highlight": text(hero.get("highlight"), 80),
                    "subtitle": text(hero.get("subtitle"), 600), "image": image(hero.get("image")), "model": choice(hero.get("model"), MODELS, "pharmacy"),
                    "primary": button(hero.get("primary")), "secondary": button(hero.get("secondary"))},
           "blocks": []}
    for b in _dicts(data.get("blocks"), MAX_BLOCKS):
        kind = choice(b.get("type"), BLOCKS, "")
        if not kind:
            raise ValidationError({"content": "Unknown section type."})
        out["blocks"].append({
            "type": kind, "title": text(b.get("title"), 160), "subtitle": text(b.get("subtitle"), 300), "body": text(b.get("body"), 8000),
            "image": image(b.get("image")), "imageSide": choice(b.get("imageSide"), {"left", "right"}, "right"),
            "layout": choice(b.get("layout"), LAYOUTS, "cards"), "animation": choice(b.get("animation"), ANIMATIONS, "up"),
            "background": choice(b.get("background"), BACKGROUNDS, "plain"), "model": choice(b.get("model"), MODELS, "none"), "button": button(b.get("button")),
            "items": [{"title": text(i.get("title"), 160), "text": text(i.get("text"), 2000), "image": image(i.get("image")), "href": link(i.get("href"))}
                      for i in _dicts(b.get("items"), MAX_ITEMS)]})
    return out


def clean_global(data):
    """Footer and contact details shared by every page of one website."""
    if not isinstance(data, dict):
        raise ValidationError({"content": "Content must be an object."})

    def coordinate(value, limit):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
        return str(round(number, 6)) if -limit <= number <= limit else ""

    return {"footerAbout": text(data.get("footerAbout"), 600), "email": text(data.get("email"), 120), "phone": text(data.get("phone"), 60),
            "whatsapp": text(data.get("whatsapp"), 30), "address": text(data.get("address"), 300), "hours": text(data.get("hours"), 300),
            "latitude": coordinate(data.get("latitude"), 90), "longitude": coordinate(data.get("longitude"), 180),
            "social": [{"title": text(i.get("title"), 40), "href": link(i.get("href"))} for i in _dicts(data.get("social"), 8)]}


PLATFORM_KEYS = {"global", "home", "features", "solutions", "pricing", "about", "faq", "contact", "support", "legal-privacy", "legal-terms",
                 "legal-payment-refund", "legal-data-protection", "legal-security", "legal-cookies"}
PHARMACY_KEYS = {"global", "home", "about", "products", "services", "institutional", "contact"}


def clean(key, data):
    return clean_global(data) if key == "global" else clean_page(data)
