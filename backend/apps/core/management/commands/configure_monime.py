from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.payments.models import PaymentProviderConfig


class Command(BaseCommand):
    help = ("Store the MONIME_* environment credentials, encrypted, as ONE pharmacy's payment configuration and enable online payments for it. "
            "Customer payments for that pharmacy then settle into this Monime space.")

    def add_arguments(self, p):
        p.add_argument("--pharmacy", required=True, help="Pharmacy slug.")
        p.add_argument("--disable", action="store_true")

    def handle(self, *a, **o):
        from apps.payments.crypto import encrypt
        from apps.tenants.models import Pharmacy
        if not (settings.MONIME_API_KEY and settings.MONIME_SPACE_ID and settings.MONIME_WEBHOOK_SECRET):
            raise CommandError("Set MONIME_API_KEY, MONIME_SPACE_ID and MONIME_WEBHOOK_SECRET first.")
        tenant = Pharmacy.objects.filter(slug=o["pharmacy"]).first()
        if tenant is None:
            raise CommandError("No such pharmacy.")
        row, _ = PaymentProviderConfig.all_objects.update_or_create(tenant=tenant, provider="monime", defaults={
            "space_id": settings.MONIME_SPACE_ID, "access_token_enc": encrypt(settings.MONIME_API_KEY),
            "webhook_secret_enc": encrypt(settings.MONIME_WEBHOOK_SECRET), "enabled": not o["disable"]})
        self.stdout.write(f"Monime {'disabled' if o['disable'] else 'enabled'} for {tenant.slug}. Webhook path to register in Monime: /api/v1/webhooks/monime/{tenant.slug}/")
