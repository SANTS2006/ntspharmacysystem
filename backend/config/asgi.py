import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from django.urls import path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi = get_asgi_application()

from apps.core.consumers import NotificationConsumer  # noqa: E402  (after Django setup)

websocket_urlpatterns = [path("ws/notifications/", NotificationConsumer.as_asgi())]
application = ProtocolTypeRouter({"http": django_asgi, "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns))})
