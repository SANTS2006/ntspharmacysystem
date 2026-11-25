from celery import shared_task

from . import services


@shared_task
def run_backup_task(kind="manual", user_id=None):
    from apps.accounts.models import User
    user = User.objects.filter(pk=user_id).first() if user_id else None
    return services.run_backup(kind=kind, user=user).pk


@shared_task
def scheduled_backup():
    try:
        return services.run_backup(kind="scheduled").pk
    except Exception as exc:  # e.g. already running or storage misconfigured: alert, do not crash the scheduler
        services.notify_failure("Scheduled backup could not start", f"{type(exc).__name__}: {exc}")
        return None


@shared_task
def purge_expired():
    return services.purge_expired()


@shared_task
def execute_restore_task(request_id, user_id, password_token):
    """Not used for password-bearing calls (passwords never go through the task queue); kept so execution can be moved to a worker via a one-time token in future."""
    raise NotImplementedError
