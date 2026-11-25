
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
    return {"website": site_url(pharmacy.slug), "admin_login": site_url(pharmacy.slug, "/admin/login")}


@transaction.atomic
def register_pharmacy(*, actor, admin_full_name, admin_email, admin_phone="", use_invitation=False, request=None,
                      **pharmacy_fields) -> Pharmacy:
    """Create tenant + default roles + main branch + admin account + credential issuance (+ audit + email)."""
    pharmacy = Pharmacy.objects.create(status=Pharmacy.Status.ACTIVE, **pharmacy_fields)
    roles = account_services.seed_default_roles(pharmacy)
    with tenant_context(pharmacy):
        from apps.medicines.services import seed_default_categories
        seed_default_categories()
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
            f"Website: {urls['website']}\nAdmin login: {urls['admin_login']}\nEmail: {admin.email}\n{credential_text}\n\n"
            "Security: never share this email. Change your password immediately and keep it private.")
    html_body = render_branded_html(
        title=f"Welcome to {settings.PLATFORM_NAME}", pharmacy=pharmacy, button=("Open admin login", urls["admin_login"]),
        paragraphs=[f'Your pharmacy "{pharmacy.name}" has been registered.', f"Website: {urls['website']}",
                    f"Registered email: {admin.email}", credential_text,
                    "Security: never share this email. Change your password at first login."])
    send_email(to=admin.email, subject=f"Your {settings.PLATFORM_NAME} pharmacy is ready", text=text,
               html_body=html_body, tenant=pharmacy, template="admin_onboarding")
    return pharmacy


@transaction.atomic
def set_status(pharmacy: Pharmacy, status: str, *, actor, reason="", request=None) -> Pharmacy:
    previous = pharmacy.status
    pharmacy.status, pharmacy.status_reason = status, reason
    pharmacy.save(update_fields=["status", "status_reason", "updated_at"])
    audit.record(f"platform.pharmacy_{status}", actor=actor, tenant=pharmacy, target=pharmacy, request=request,
                 previous=previous, reason=reason)
    return pharmacy
