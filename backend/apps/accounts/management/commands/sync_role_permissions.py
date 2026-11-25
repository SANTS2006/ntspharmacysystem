"""Add permissions introduced after a pharmacy was onboarded to its SYSTEM roles (union with defaults; never removes).
Run after deploying a release that adds permission codenames."""
from django.core.management.base import BaseCommand

from apps.accounts.models import Role
from apps.accounts.permissions_registry import DEFAULT_ROLE_PERMISSIONS


class Command(BaseCommand):
    help = "Grant newly added default permissions to existing system roles."

    def handle(self, *args, **opts):
        changed = 0
        for role in Role.objects.filter(is_system=True):
            wanted = set(DEFAULT_ROLE_PERMISSIONS.get(role.code, set()))
            missing = wanted - set(role.permissions)
            if missing and role.code != "customer":
                role.permissions = sorted(set(role.permissions) | missing)
                role.save(update_fields=["permissions", "updated_at"])
                changed += 1
        self.stdout.write(f"Updated {changed} role(s).")
