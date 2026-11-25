from celery import shared_task

from .models import EmailLog
from .services import deliver


@shared_task(bind=True, max_retries=4, default_retry_delay=60, retry_backoff=True)
def deliver_email(self, log_id: int, text: str, html_body: str = ""):
    entry = EmailLog.objects.get(pk=log_id)
    try:
        deliver(entry, text, html_body)
    except Exception as exc:
        if self.request.is_eager:  # dev/eager mode: record failure, don't break the caller
            return
        raise self.retry(exc=exc)
