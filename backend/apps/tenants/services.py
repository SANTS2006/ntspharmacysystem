
from django.conf import settings
from django.db import transaction

from apps.accounts import services as account_services
from apps.accounts.models import User
from apps.audit import services as audit
from apps.core.tenant_context import tenant_context
from apps.notifications.services import render_branded_html, send_email

from .models import Branch, Pharmacy


def pharmacy_urls(pharmacy: Pharmacy) -> dict:
    from apps.core.links import site_url
    return {"website": site_url(pharmacy.slug), "admin_login": site_url(pharmacy.slug, "/login")}


@transaction.atomic
def register_pharmacy(*, actor, admin_full_name, admin_email, admin_phone="", use_invitation=False, request=None,
                      **pharmacy_fields) -> Pharmacy:
    """Create tenant + default roles + main branch + admin account + credential issuance (+ audit + email)."""
    pharmacy = Pharmacy.objects.create(status=Pharmacy.Status.ACTIVE, **pharmacy_fields)
    roles = account_services.seed_default_roles(pharmacy)
    with tenant_context(pharmacy):
        Branch.objects.create(name="Main Branch", code="MAIN", address=pharmacy.address,
                              phone=pharmacy.contact_phone, email=pharmacy.contact_email)
    admin = User.objects.create_user(
        email=admin_email, tenant=pharmacy, role=roles["pharmacy_admin"], full_name=admin_full_name,
        phone=admin_phone, created_by=actor)
    urls = pharmacy_urls(pharmacy)
    if use_invitation:
        admin.set_unusable_password()
        admin.must_change_password = True
        admin.save()
        token = account_services.create_invitation(admin)
        credential_text = f"Set your password using this one-time link: {settings.FRONTEND_URL}/accept-invitation?token={token}"
        method = "invitation"
    else:
        temp = account_services.build_default_password(pharmacy.name)
        account_services.issue_temporary_credentials(admin, temp)
        credential_text = (f"Temporary password: {temp}\nIt expires in {settings.TEMP_CREDENTIAL_TTL_HOURS} hours "
                           "and you will be required to change it at first login.")
        method = "temporary_password"
    audit.record("platform.pharmacy_registered", actor=actor, tenant=pharmacy, target=pharmacy, request=request,
                 slug=pharmacy.slug)
    audit.record("auth.credentials_issued", actor=actor, tenant=pharmacy, target=admin, request=request, method=method)
    text = (f"Welcome to {settings.PLATFORM_NAME}!\n\nYour pharmacy \"{pharmacy.name}\" has been registered.\n"
            f"Website: {urls['website']}\nSign in: {urls['admin_login']}\nEmail: {admin.email}\n{credential_text}\n\n"
            "Security: never share this email. Change your password immediately and keep it private.")
    html_body = render_branded_html(
        title=f"Welcome to {settings.PLATFORM_NAME}", pharmacy=pharmacy, button=("Sign in to your pharmacy", urls["admin_login"]),
        paragraphs=[f'Your pharmacy "{pharmacy.name}" has been registered.', f"Website: {urls['website']}",
                    f"Registered email: {admin.email}", credential_text,
                    "Security: never share this email. Change your password at first login."])
    send_email(to=admin.email, subject=f"Your {settings.PLATFORM_NAME} pharmacy is ready", text=text,
               html_body=html_body, tenant=pharmacy, template="admin_onboarding")
    from apps.notifications import inapp
    inapp.push([admin], kind="account", level="success", title=f"Welcome to {settings.PLATFORM_NAME}",
               body=f"{pharmacy.name} is ready. Start by checking your pharmacy settings and branches.", link="/dashboard")
    inapp.push(inapp.platform_admins(), kind="platform", title="New pharmacy registered", body=pharmacy.name, link=f"/pharmacies/{pharmacy.pk}", exclude=actor)
    return pharmacy


@transaction.atomic
def update_administrator(pharmacy: Pharmacy, *, actor, request=None, admin_full_name=None, admin_email=None, admin_phone=None, use_invitation=False):
    """Edit the pharmacy's first administrator. Changing the sign-in address ends that account's sessions."""
    from rest_framework.exceptions import ValidationError
    admin = User.objects.filter(tenant=pharmacy, role__code="pharmacy_admin").order_by("date_joined", "pk").first()
    if admin is None:
        raise ValidationError({"admin_email": "This pharmacy has no administrator account."})
    changed = []
    if admin_full_name and admin_full_name != admin.full_name:
        admin.full_name = admin_full_name
        changed.append("full_name")
    if admin_phone is not None and admin_phone != admin.phone:
        admin.phone = admin_phone
        changed.append("phone")
    email = (admin_email or "").strip().lower()
    email_changed = bool(email) and email != admin.email
    if email_changed:
        if User.objects.filter(tenant=pharmacy, email=email).exclude(pk=admin.pk).exists():
            raise ValidationError({"admin_email": "Another account in this pharmacy already uses this email."})
        old, admin.email = admin.email, email
        admin.credential_version += 1
        changed += ["email", "credential_version"]
    if changed:
        admin.save(update_fields=changed)
        audit.record("platform.administrator_updated", actor=actor, tenant=pharmacy, target=admin, request=request, fields=sorted(changed))
    if email_changed:
        send_email(to=old, subject="Your administrator email was changed", tenant=pharmacy, template="email_change_notice",
                   text=f"The sign-in email for the {pharmacy.name} administrator was changed to {email} by the platform team. Contact them if this is unexpected.")
    if use_invitation:
        link = f"{settings.FRONTEND_URL.rstrip('/')}/accept-invitation?token={account_services.create_invitation(admin)}"
        send_email(to=admin.email, subject=f"Set your {pharmacy.name} password", tenant=pharmacy, template="admin_onboarding",
                   text=f"Use this one-time link to set your password: {link}",
                   html_body=render_branded_html(title="Set your password", pharmacy=pharmacy, button=("Set my password", link),
                                                 paragraphs=["The platform team sent you a new one-time link to set your password."]))
    return admin


@transaction.atomic
def set_status(pharmacy: Pharmacy, status: str, *, actor, reason="", request=None) -> Pharmacy:
    previous = pharmacy.status
    pharmacy.status, pharmacy.status_reason = status, reason
    pharmacy.save(update_fields=["status", "status_reason", "updated_at"])
    audit.record(f"platform.pharmacy_{status}", actor=actor, tenant=pharmacy, target=pharmacy, request=request,
                 previous=previous, reason=reason)
    return pharmacy
