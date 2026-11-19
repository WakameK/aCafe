"""
ASGI config for mysite project.

HTTPは通常のDjango、WebSocketはChannels + Redisチャンネルレイヤーで捌く。
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

import desk.routing  # noqa: E402
import space.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(
                    desk.routing.websocket_urlpatterns
                    + space.routing.websocket_urlpatterns
                )
            )
        ),
    }
)