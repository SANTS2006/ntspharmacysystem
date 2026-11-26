"""Customer accounts, email verification, Google sign-in, checkout and the order workflow."""
import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.accounts.models import Role, User
from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.core.tenant_context import get_current_tenant, tenant_context
from apps.inventory import services as inv
from apps.inventory.models import Batch
from apps.medicines.models import Medicine
from apps.notifications import inapp
from apps.notifications.services import render_branded_html, send_email
from apps.procurement.models import next_number
from apps.tenants.models import Branch

from .models import CustomerProfile, EmailVerification, Order, OrderEvent, OrderLine, QrRequest, QrRequestItem, ZERO

S = Order.Status
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # alphanumeric, without look-alikes (0/O, 1/I)


class TooManyRequests(APIException):
    status_code = 429
    default_code = "too_many_requests"
    default_detail = "Please wait before trying again."


class ServiceUnavailable(APIException):
    status_code = 503
    default_code = "google_not_configured"
    default_detail = "Google sign-in is not configured."


def q2(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def tsetting(key, default):
    return (get_current_tenant().settings or {}).get(key, default)


# ======================= email verification =======================
def _hash_code(user, code: str) -> str:
    return hashlib.sha256(f"{user.pk}:{code.upper()}:{settings.SECRET_KEY}".encode()).hexdigest()


@transaction.atomic
def send_verification_code(user: User, *, respect_cooldown=True) -> None:
    ev = EmailVerification.objects.select_for_update(of=("self",)).filter(user=user).first()
    now = timezone.now()
    if ev and respect_cooldown and (now - ev.last_sent_at).total_seconds() < settings.EMAIL_CODE_RESEND_SECONDS:
        raise TooManyRequests(f"Please wait {settings.EMAIL_CODE_RESEND_SECONDS} seconds before requesting another code.")
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    fields = dict(code_hash=_hash_code(user, code), expires_at=now + timedelta(minutes=settings.EMAIL_CODE_TTL_MINUTES), attempts=0, last_sent_at=now, consumed_at=None)
    if ev:
        for k, v in fields.items():
            setattr(ev, k, v)
        ev.save()
    else:
        EmailVerification.objects.create(user=user, **fields)
    tenant = user.tenant
    text = f"Your {tenant.name} verification code is {code}. It expires in {settings.EMAIL_CODE_TTL_MINUTES} minutes. If you did not request it, ignore this email."
    send_email(to=user.email, subject=f"Your verification code: {code}", text=text, tenant=tenant, template="email_verification",
               html_body=render_branded_html(title="Verify your email", pharmacy=tenant, paragraphs=["Use this code to verify your email address.", f"It expires in {settings.EMAIL_CODE_TTL_MINUTES} minutes. If you did not request it, ignore this email."], code=code))


def verify_email_code(user: User, code: str, request=None) -> str:
    """Returns 'ok' | 'bad' | 'locked'. Failures are RETURNED, not raised: raising would roll back the request transaction
    (ATOMIC_REQUESTS) and silently discard the attempt counter, defeating brute-force protection."""
    with transaction.atomic():
        ev = EmailVerification.objects.select_for_update(of=("self",)).filter(user=user).first()
        if user.email_verified:
            return "ok"
        if ev is None or ev.consumed_at or ev.expires_at < timezone.now():
            return "bad"
        if ev.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
            return "locked"
        if not hmac.compare_digest(ev.code_hash, _hash_code(user, (code or "").strip())):
            ev.attempts += 1
            ev.save(update_fields=["attempts"])
            return "bad"
        ev.consumed_at = timezone.now()  # a used code can never be used again
        ev.save(update_fields=["consumed_at"])
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        audit.record("customer.email_verified", actor=user, tenant=user.tenant, request=request)
        inapp.push_staff(user.tenant_id, "customer.view", None, kind="customer", title="New customer registered",
                         body=f"{user.full_name} ({user.email}) verified their account.", link=f"/customers/{user.pk}")
        inapp.push([user], kind="account", level="success", title=f"Welcome to {user.tenant.name}",
                   body="Your account is ready. Complete your profile so the pharmacy can serve you better.", link="/settings")
        return "ok"


# ======================= registration / Google =======================
def _customer_role(tenant) -> Role:
    return Role.objects.get(tenant=tenant, code="customer")


@transaction.atomic
def register_customer(*, tenant, email, password, full_name, phone="", terms_accepted: bool, request=None) -> User:
    if not terms_accepted:
        raise ValidationError({"terms_accepted": "You must agree to the Terms of Use and Privacy Policy."})
    email = email.strip().lower()
    if User.objects.filter(tenant=tenant, email=email).exists():
        # Deliberately vague: do not confirm which emails are registered.
        raise ValidationError({"email": "We could not create an account with these details. If you already have one, sign in or reset your password."})
    user = User.objects.create_user(email=email, password=password, tenant=tenant, role=_customer_role(tenant), full_name=full_name, phone=phone)
    CustomerProfile.objects.create(user=user, tenant=tenant, terms_version=settings.TERMS_VERSION, terms_accepted_at=timezone.now(), terms_accepted_via="password")
    audit.record("customer.registered", actor=user, tenant=tenant, request=request, terms_version=settings.TERMS_VERSION)
    send_verification_code(user, respect_cooldown=False)
    return user


def verify_google_id_token(token: str) -> dict:
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        raise ServiceUnavailable()
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": token})
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 (fixed https host)
            info = json.loads(r.read())
    except (urllib.error.URLError, ValueError):
        raise ValidationError({"id_token": "Google sign-in could not be verified."})
    if info.get("aud") != settings.GOOGLE_OAUTH_CLIENT_ID or str(info.get("email_verified")).lower() != "true" or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValidationError({"id_token": "Google sign-in could not be verified."})
    return info


@transaction.atomic
def google_sign_in(*, tenant, id_token, terms_accepted: bool, request=None) -> User:
    """Existing customers sign in without the checkbox; NEW accounts need terms_accepted. Staff accounts never sign in this way."""
    info = verify_google_id_token(id_token)
    email, sub = info["email"].lower(), info["sub"]
    user = User.objects.filter(tenant=tenant, email=email).select_related("role").first()
    if user is not None:
        if user.role is None or user.role.code != "customer":
            raise BusinessRuleViolation("This email belongs to a staff account. Sign in with your password.")
        if not user.is_active:
            raise ValidationError({"id_token": "This account is disabled."})
        prof = user.customer_profile
        if prof.google_sub and prof.google_sub != sub:
            raise ValidationError({"id_token": "Google sign-in could not be verified."})
        if not prof.google_sub:
            prof.google_sub = sub
            prof.save(update_fields=["google_sub", "updated_at"])
        if not user.email_verified:  # Google verified this address
            user.email_verified = True
            user.save(update_fields=["email_verified"])
        audit.record("auth.google_login", actor=user, tenant=tenant, request=request)
        return user
    if not terms_accepted:
        raise ValidationError({"terms_accepted": "You must agree to the Terms of Use and Privacy Policy to create an account."})
    user = User.objects.create_user(email=email, password=None, tenant=tenant, role=_customer_role(tenant), full_name=info.get("name") or email, email_verified=True)
    user.set_unusable_password()
    user.save()
    CustomerProfile.objects.create(user=user, tenant=tenant, google_sub=sub, terms_version=settings.TERMS_VERSION, terms_accepted_at=timezone.now(), terms_accepted_via="google")
    audit.record("customer.registered", actor=user, tenant=tenant, request=request, via="google", terms_version=settings.TERMS_VERSION)
    return user


# ======================= catalogue helpers =======================
def online_visible(qs=None):
    qs = qs if qs is not None else Medicine.objects.all()
    return qs.filter(status="active", is_online_visible=True).exclude(classification="controlled")


def saleable_stock(medicine, branch) -> int:
    from django.db.models import Sum
    return Batch.objects.filter(medicine=medicine, branch=branch).filter(inv.saleable_q()).aggregate(t=Sum("quantity_available"))["t"] or 0


# ======================= orders =======================
DEFAULT_FLOW = {
    S.PENDING: {S.AWAITING_PRESCRIPTION, S.AWAITING_PAYMENT, S.CANCELLED},
    S.AWAITING_PRESCRIPTION: {S.PRESCRIPTION_APPROVED, S.PRESCRIPTION_REJECTED, S.CANCELLED},
    S.PRESCRIPTION_APPROVED: {S.AWAITING_PAYMENT, S.CANCELLED},
    S.PRESCRIPTION_REJECTED: {S.CANCELLED},
    S.AWAITING_PAYMENT: {S.PAYMENT_CONFIRMED, S.CANCELLED},
    S.PAYMENT_CONFIRMED: {S.PROCESSING, S.REFUND_REQUESTED},  # paid orders are unwound through a refund request, never a plain cancel
    S.PROCESSING: {S.PREPARING, S.REFUND_REQUESTED},
    S.PREPARING: {S.READY_FOR_PICKUP, S.OUT_FOR_DELIVERY, S.REFUND_REQUESTED},
    S.READY_FOR_PICKUP: {S.COMPLETED, S.REFUND_REQUESTED},
    S.OUT_FOR_DELIVERY: {S.DELIVERED},
    S.DELIVERED: {S.COMPLETED, S.REFUND_REQUESTED},
    S.COMPLETED: {S.REFUND_REQUESTED},
    S.REFUND_REQUESTED: {S.REFUNDED, S.COMPLETED},
}
SYSTEM_ONLY = {S.AWAITING_PRESCRIPTION, S.PRESCRIPTION_APPROVED, S.PRESCRIPTION_REJECTED, S.AWAITING_PAYMENT}  # set by the workflow itself
CUSTOMER_CAN = {S.CANCELLED: {S.PENDING, S.AWAITING_PRESCRIPTION, S.PRESCRIPTION_APPROVED, S.PRESCRIPTION_REJECTED, S.AWAITING_PAYMENT},
                S.REFUND_REQUESTED: {S.DELIVERED, S.COMPLETED, S.READY_FOR_PICKUP}}
PAYMENT_METHODS = {"pickup": "cash_on_pickup", "delivery": "cash_on_delivery"}
LABELS = {s.value: s.label if hasattr(s, "label") else s.value for s in S}


def flow_for(tenant) -> dict:
    """Default transitions, optionally overridden per pharmacy via settings['order_transitions'] = {from: [to, ...]}."""
    flow = {k.value: {v.value for v in vs} for k, vs in DEFAULT_FLOW.items()}
    valid = {s.value for s in S}
    for src, targets in ((tenant.settings or {}).get("order_transitions") or {}).items():
        if src in valid and isinstance(targets, list) and set(targets) <= valid:
            flow[src] = set(targets)
    return flow


def _notify(order: Order, text: str):
    prefs = getattr(order.customer, "customer_profile", None)
    if prefs and not prefs.notification_prefs.get("email_orders", True):
        return
    t = get_current_tenant()
    from apps.core.links import site_url
    send_email(to=order.customer.email, subject=f"Order {order.reference_number}: {text}", text=f"Your order {order.reference_number} is now: {text}.", tenant=t,
               template="order_status", html_body=render_branded_html(title="Order update", pharmacy=t, paragraphs=[f"Hello {order.customer.full_name}, your order has moved to a new step."],
                                             details=[("Order", order.reference_number), ("Status", text.capitalize()), ("Total", str(order.total)), ("Branch", order.branch.name)],
                                             button=("Track your order", site_url(t.slug, f"/account/orders/{order.pk}"))))


def _event(order, to, actor, note=""):
    first_step = order.status == S.PENDING  # the move right after placing is covered by the "order placed" notification
    OrderEvent.objects.create(order=order, from_status=order.status, to_status=to, actor=actor, note=note[:300])
    order.status = to
    order.save(update_fields=["status", "updated_at"])
    _notify(order, to.replace("_", " "))
    if not first_step:
        label = to.replace("_", " ")
        level = ("success" if to in ("payment_confirmed", "ready_for_pickup", "delivered", "completed", "prescription_approved")
                 else "danger" if to in ("cancelled", "prescription_rejected") else "info")
        inapp.push([order.customer], kind="order", level=level, title=f"Order {order.reference_number}: {label}",
                   body=note or f"Your order is now {label}.", link=f"/orders/{order.pk}", exclude=actor)
        if to in ("payment_confirmed", "refund_requested", "cancelled"):
            inapp.push_staff(order.tenant_id, "sales.refund" if to == "refund_requested" else "order.manage", order.branch_id, kind="order",
                             level="warning" if to == "refund_requested" else level, title=f"Order {order.reference_number}: {label}",
                             body=note, link="/orders", exclude=actor)
    from apps.core.realtime import notify_topic
    notify_topic(order.tenant_id, order.branch_id, "orders", "order.updated", {"id": order.pk, "reference": order.reference_number, "status": to}, users=[order.customer_id])


@transaction.atomic
def create_order(*, customer, branch, fulfilment, items, payment_method, idempotency_key, delivery_address="", notes="") -> tuple[Order, bool]:
    key = (idempotency_key or "").strip()
    if not key:
        raise ValidationError({"idempotency_key": "An Idempotency-Key is required."})
    existing = Order.objects.filter(idempotency_key=key).first()
    if existing:
        if existing.customer_id != customer.pk:
            raise BusinessRuleViolation("This idempotency key belongs to another order.")
        return existing, False
    if branch.status != branch.Status.ACTIVE:
        raise ValidationError({"branch": "This branch is not available."})
    if fulfilment not in PAYMENT_METHODS:
        raise ValidationError({"fulfilment": "Choose pickup or delivery."})
    from apps.payments.services import ONLINE, provider_ready
    allowed = {PAYMENT_METHODS[fulfilment]} | ({ONLINE} if provider_ready() else set())
    if payment_method not in allowed:
        raise ValidationError({"payment_method": "That payment method is not available. Choose pay on pickup/delivery" + (" or pay online." if provider_ready() else ".")})
    if fulfilment == "delivery" and not delivery_address.strip():
        raise ValidationError({"delivery_address": "Enter a delivery address."})
    if not items:
        raise ValidationError({"items": "Your cart is empty."})
    seen, calc, subtotal, tax_total, needs_rx = set(), [], ZERO, ZERO, False
    for it in items:
        m = it["medicine"]
        if m.pk in seen:
            raise ValidationError({"items": f"{m.name} appears more than once."})
        seen.add(m.pk)
        if not online_visible(Medicine.objects.filter(pk=m.pk)).exists():
            raise ValidationError({"items": f"{m.name} is not available for online ordering."})
        if saleable_stock(m, branch) < it["quantity"]:
            raise BusinessRuleViolation(f"{m.name}: not enough stock at this branch.")
        net = q2(m.selling_price * it["quantity"])
        tax = q2(net * m.tax_rate / 100)
        calc.append((m, it["quantity"], net, tax))
        subtotal += net
        tax_total += tax
        needs_rx = needs_rx or m.requires_prescription
    fee = q2(Decimal(str(tsetting("delivery_fee", 0)))) if fulfilment == "delivery" else ZERO
    try:
        with transaction.atomic():
            order = Order.objects.create(reference_number=next_number("ORD"), idempotency_key=key, customer=customer, branch=branch, fulfilment=fulfilment,
                                         delivery_address=delivery_address[:300], payment_method=payment_method, subtotal=subtotal, tax_total=tax_total,
                                         delivery_fee=fee, total=subtotal + tax_total + fee, requires_prescription=needs_rx, notes=notes[:300])
    except IntegrityError:
        return Order.objects.get(idempotency_key=key), False
    for m, qty, net, tax in calc:
        OrderLine.objects.create(order=order, medicine=m, quantity=qty, unit_price=m.selling_price, tax_amount=tax, line_total=net + tax)
    OrderEvent.objects.create(order=order, from_status="", to_status=S.PENDING, actor=customer, note="Order placed")
    _event(order, S.AWAITING_PRESCRIPTION if needs_rx else S.AWAITING_PAYMENT, None, "Prescription needed" if needs_rx else "Awaiting payment")
    audit.record("order.created", actor=customer, target=order, branch_id=branch.pk, reference=order.reference_number, total=str(order.total))
    from apps.core.realtime import notify_topic
    notify_topic(order.tenant_id, branch.pk, "orders", "order.created", {"id": order.pk, "reference": order.reference_number, "status": order.status})
    inapp.push_staff(order.tenant_id, "order.manage", branch.pk, kind="order", title=f"New online order {order.reference_number}",
                     body=f"{customer.full_name} placed an order of {order.total} for {fulfilment} at {branch.name}.", link="/orders")
    next_step = ("Upload your prescription to continue." if needs_rx else "Complete your payment to continue." if payment_method == "monime"
                 else "The pharmacy will prepare it.")
    inapp.push([customer], kind="order", level="success", title=f"Order {order.reference_number} placed", body=f"We received your order. {next_step}",
               link=f"/orders/{order.pk}")
    return order, True


@transaction.atomic
def transition(order_id, to, *, actor, kind, note="") -> Order:
    """kind: 'staff' | 'customer' | 'system'. Valid moves are enforced here, never by the client."""
    order = Order.objects.select_for_update(of=("self",)).select_related("customer", "branch").get(pk=order_id)
    to = str(to)
    if to not in {s.value for s in S}:
        raise ValidationError({"status": "Unknown status."})
    if to not in flow_for(get_current_tenant()).get(order.status, set()):
        raise BusinessRuleViolation(f"An order that is {order.status.replace('_', ' ')} cannot move to {to.replace('_', ' ')}.")
    if kind == "customer":
        if order.status not in CUSTOMER_CAN.get(to, set()):
            raise BusinessRuleViolation("You can no longer do that. Please contact the pharmacy.")
    elif kind == "staff" and to in SYSTEM_ONLY:
        raise BusinessRuleViolation(f"'{to.replace('_', ' ')}' is set automatically by the workflow.")
    if to == S.PAYMENT_CONFIRMED and kind == "staff" and not order.payment_method.startswith("cash_on_"):
        raise BusinessRuleViolation("Payment for this order must be confirmed by the payment provider.")  # staff cannot assert gateway payments
    if to == S.READY_FOR_PICKUP and order.fulfilment != "pickup":
        raise BusinessRuleViolation("Only pickup orders can be marked ready for pickup.")
    if to == S.OUT_FOR_DELIVERY and order.fulfilment != "delivery":
        raise BusinessRuleViolation("Only delivery orders can go out for delivery.")
    if to == S.PROCESSING:
        _commit_stock(order, actor)
    if to == S.CANCELLED and order.lines.filter(stock_deducted=True).exists():
        raise BusinessRuleViolation("Stock has already been committed for this order.")
    _event(order, to, actor, note)
    if to == S.PAYMENT_CONFIRMED:
        from apps.accounting.posting import post_order_payment
        from apps.payments.services import issue_order_receipt
        post_order_payment(order)
        issue_order_receipt(order)
    if to in (S.DELIVERED, S.COMPLETED):
        from apps.accounting.posting import post_order_revenue
        post_order_revenue(order)  # revenue is recognised on fulfilment, not on payment
    audit.record("order.status_changed", actor=actor, target=order, branch_id=order.branch_id, to=to, by=kind)
    return order


def _commit_stock(order: Order, actor) -> None:
    """At processing: non-prescription lines are deducted FEFO; prescription lines must already have been dispensed by a pharmacist."""
    rx_lines = [l for l in order.lines.select_related("medicine") if l.medicine.requires_prescription]
    if rx_lines:
        rx = order.prescription
        if rx is None or rx.status not in ("dispensed", "partially_dispensed"):
            raise BusinessRuleViolation("A pharmacist must review and dispense the prescription items before processing.")
    for line in order.lines.select_related("medicine"):
        if line.medicine.requires_prescription or line.stock_deducted:
            continue
        inv.deduct_fefo(medicine=line.medicine, branch=order.branch, quantity=line.quantity, user=actor, ref_type="online_order", ref_id=order.reference_number)
        line.stock_deducted = True
        line.save(update_fields=["stock_deducted", "updated_at"])


@transaction.atomic
def attach_prescription(order_id, *, customer, prescriber_name, prescription_date, document) -> Order:
    from apps.prescriptions.models import Patient
    from apps.prescriptions.services import create_prescription
    from apps.prescriptions.validators import validate_prescription_file
    order = Order.objects.select_for_update(of=("self",)).get(pk=order_id, customer=customer)
    if not order.requires_prescription or order.status != S.AWAITING_PRESCRIPTION or order.prescription_id:
        raise BusinessRuleViolation("A prescription cannot be attached to this order.")
    try:
        validate_prescription_file(document)
    except Exception as e:
        raise ValidationError({"document": list(getattr(e, "messages", [str(e)]))})
    patient = Patient.objects.filter(user=customer).first() or Patient.objects.create(user=customer, full_name=customer.full_name, phone=customer.phone, branch=order.branch)
    rx_items = [{"medicine": l.medicine, "dosage": "As prescribed", "frequency": "As prescribed", "quantity_prescribed": l.quantity}
                for l in order.lines.select_related("medicine") if l.medicine.requires_prescription]
    rx = create_prescription(patient=patient, branch=order.branch, user=customer, items=rx_items, prescriber_name=prescriber_name, prescription_date=prescription_date,
                             notes=f"Uploaded by customer for order {order.reference_number}")
    rx.document.save(f"{rx.reference_number}-{document.name}"[:100], document)
    order.prescription = rx
    order.save(update_fields=["prescription", "updated_at"])
    OrderEvent.objects.create(order=order, from_status=order.status, to_status=order.status, actor=customer, note="Prescription uploaded for pharmacist review")
    audit.record("order.prescription_uploaded", actor=customer, target=order, branch_id=order.branch_id, prescription=rx.reference_number)
    return order


def on_prescription_decision(rx, approved: bool, actor) -> None:
    """Called by the prescription workflow so the customer's order follows the pharmacist's decision."""
    for order in Order.objects.select_for_update(of=("self",)).filter(prescription=rx, status=S.AWAITING_PRESCRIPTION):
        if approved:
            _event(order, S.PRESCRIPTION_APPROVED, actor, "Prescription approved by pharmacist")
            _event(order, S.AWAITING_PAYMENT, None, "Awaiting payment")
        else:
            _event(order, S.PRESCRIPTION_REJECTED, actor, rx.rejection_reason[:300])


# ======================= QR menu =======================
def ensure_qr_token(branch: Branch) -> str:
    if not branch.qr_token:
        branch.qr_token = secrets.token_urlsafe(16)
        branch.save(update_fields=["qr_token", "updated_at"])
        audit.record("branch.qr_generated", actor=None, tenant=branch.tenant, target=branch, branch_id=branch.pk)
    return branch.qr_token


def resolve_qr(token: str) -> Branch:
    branch = Branch.all_objects.select_related("tenant").filter(qr_token=token, status="active").first()
    if branch is None or not branch.tenant.is_active_tenant:
        from rest_framework.exceptions import NotFound
        raise NotFound()
    return branch


def create_qr_request(branch: Branch, *, name, phone, kind, note, items) -> QrRequest:
    with tenant_context(branch.tenant):
        if not name.strip() or not phone.strip():
            raise ValidationError({"detail": "Enter your name and phone number."})
        if kind == "shopping" and not items:
            raise ValidationError({"items": "Add at least one product."})
        if len(items) > 30:
            raise ValidationError({"items": "Too many products in one request."})
        req = QrRequest.objects.create(branch=branch, kind=kind, customer_name=name[:150], customer_phone=phone[:30], note=note[:500])
        seen, rx = set(), False
        for it in items:
            m = it["medicine"]
            if m.pk in seen or not online_visible(Medicine.objects.filter(pk=m.pk)).exists():
                raise ValidationError({"items": f"{m.name} is not available."})
            seen.add(m.pk)
            rx = rx or m.requires_prescription
            QrRequestItem.objects.create(request=req, medicine=m, quantity=it["quantity"])
        if rx:
            req.requires_prescription = True
            req.save(update_fields=["requires_prescription", "updated_at"])
        audit.record("qr_request.created", actor=None, tenant=branch.tenant, target=req, branch_id=branch.pk)
        from apps.core.realtime import notify_topic
        notify_topic(branch.tenant_id, branch.pk, "qr", "qr_request.created", {"id": req.pk, "kind": req.kind})
        inapp.push_staff(branch.tenant_id, "order.manage", branch.pk, kind="order", title=f"New QR {req.kind} request",
                         body=f"{req.customer_name} ({req.customer_phone}) sent a request at {branch.name}.", link="/orders")
        return req
