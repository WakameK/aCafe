import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

# 1. まず環境変数をセット
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')

# 2. 次に get_asgi_application() を実行して Django を完全に初期化する（超重要！）
django_asgi_app = get_asgi_application()

# 3. Djangoの初期化が「終わった後」に、モデルを読み込む自作の Consumer をインポートする
from desk.consumers import ChatConsumer  

# 4. 最後にルーティングを定義する
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter([
        path("ws/desk/<int:room_id>/", ChatConsumer.as_asgi()),
    ]),
})