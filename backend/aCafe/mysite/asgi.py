"""
ASGI config for mysite project.

HTTPは通常のDjango、WebSocketはChannels + Redisチャンネルレイヤーで捌く。
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")

# Djangoアプリの設定を先に読み込んでおく(Channelsのconsumerがモデルをimportするため)
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402

import desk.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": OriginValidator(
            URLRouter(desk.routing.websocket_urlpatterns),
            settings.WS_ALLOWED_ORIGINS,
        ),
    }
)
