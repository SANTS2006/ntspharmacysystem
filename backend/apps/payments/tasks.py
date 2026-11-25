from celery import shared_task

from . import services


@shared_task
def reconcile_all():
    """Beat task: for every pharmacy with online payments enabled, resolve payments whose webhook never arrived."""
    return {t.slug: services.reconcile(t) for t in services.tenants_with_online_payments()}
