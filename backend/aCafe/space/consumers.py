import random
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import SpaceRoom

# 部屋ごとのプレイヤー状態 { room_slug: { player_id: state } }
# ※ プロセス内メモリなので、ASGIサーバー1プロセス運用が前提(MVP用)
#    views.py からも人数表示のために参照する
ROOMS: dict[str, dict[str, dict]] = {}


class SpaceConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.joined = False
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.group_name = f"space_{self.room_name}"
        self.player_id = uuid.uuid4().hex[:8]

        await self.accept()

        # DBに登録されていない部屋には入れない
        if not await self._room_exists():
            await self.send_json({"type": "room_not_found"})
            await self.close()
            return

        room = ROOMS.setdefault(self.room_name, {})

        # 重ならないよう少しずらした位置に出現させる
        state = {
            "id": self.player_id,
            "x": random.uniform(-2.0, 2.0),
            "y": 1.0,
            "z": random.uniform(-2.0, 2.0),
            "ry": 0.0,
        }
        room[self.player_id] = state
        self.joined = True

        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # 本人には自分のIDと出現位置、すでにいる人の一覧を送る
        others = [p for pid, p in room.items() if pid != self.player_id]
        await self.send_json({"type": "welcome", **state, "players": others})

        # ほかの人には入室を知らせる
        await self._broadcast({"type": "player_joined", **state})

    async def disconnect(self, code):
        if not self.joined:
            return

        room = ROOMS.get(self.room_name, {})
        room.pop(self.player_id, None)
        if not room:
            ROOMS.pop(self.room_name, None)

        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self._broadcast({"type": "player_left", "id": self.player_id})

    async def receive_json(self, content, **kwargs):
        if content.get("type") != "move":
            return

        state = ROOMS.get(self.room_name, {}).get(self.player_id)
        if state is None:
            return

        try:
            state["x"] = float(content["x"])
            state["y"] = float(content["y"])
            state["z"] = float(content["z"])
            state["ry"] = float(content["ry"])
        except (KeyError, TypeError, ValueError):
            return

        await self._broadcast({"type": "player_moved", **state})

    # --- 内部処理 ---

    @database_sync_to_async
    def _room_exists(self) -> bool:
        return SpaceRoom.objects.filter(slug=self.room_name).exists()

    async def _broadcast(self, message: dict):
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "space.broadcast", "message": message, "sender": self.player_id},
        )

    async def space_broadcast(self, event):
        # 自分が送ったものは自分には返さない
        if event.get("sender") == self.player_id:
            return
        await self.send_json(event["message"])