from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print new Fernet keys for FIELD_ENCRYPTION_KEY / BACKUP_ENCRYPTION_KEY and a Django SECRET_KEY. Copy them into your environment; they are not stored anywhere."

    def handle(self, *a, **o):
        from django.core.management.utils import get_random_secret_key
        self.stdout.write(f"FIELD_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
        self.stdout.write(f"BACKUP_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
        self.stdout.write(f"DJANGO_SECRET_KEY={get_random_secret_key()}")
