from django.core.management.base import BaseCommand, CommandError

from apps.notifications.services import render_branded_html, send_email


class Command(BaseCommand):
    help = "Send one real email through the configured provider (Brevo when BREVO_API_KEY is set) to verify delivery and the templates."

    def add_arguments(self, p):
        p.add_argument("--to", required=True)
        p.add_argument("--pharmacy", help="Pharmacy slug: use that pharmacy's template instead of the platform template.")

    def handle(self, *a, **o):
        from apps.tenants.models import Pharmacy
        tenant = None
        if o["pharmacy"]:
            tenant = Pharmacy.objects.filter(slug=o["pharmacy"]).first()
            if tenant is None:
                raise CommandError("No such pharmacy.")
        subject = "Test email from " + (tenant.name if tenant else "the platform")
        paras = ["This is a delivery test. If you can read this, email sending works.", "No action is needed."]
        entry = send_email(to=o["to"], subject=subject, text="\n\n".join(paras), tenant=tenant, template="test",
                           html_body=render_branded_html(title="Email delivery test", paragraphs=paras, pharmacy=tenant, code="123456"))
        entry.refresh_from_db()
        self.stdout.write(f"Queued/sent: status={entry.status} provider={entry.provider} error={entry.last_error or '-'}")
