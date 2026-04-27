# ============================================================
# WebSocketコンシューマー
# ============================================================
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json
from .models import Room, Message
from sosuke.models import Users

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name = f"room_{self.room_id}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data["message"]
        user_name = data["user"]

        # DBにメッセージを保存
        await self.save_message(self.room_id, user_name, message)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
                "user": user_name,
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "user": event["user"],
        }))

    @database_sync_to_async
    def save_message(self, room_id, user_name, content):
        try:
            room = Room.objects.get(id=room_id)
            user = Users.objects.get(name=user_name)
            Message.objects.create(
                room=room,
                user=user,
                content=content
            )
        except (Room.DoesNotExist, Users.DoesNotExist):
            pass  # ルームまたはユーザーが見つからない場合は何もしない
