import math
import random
import time
import uuid
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from . import fire
from .models import SpaceRoom

# 部屋ごとのプレイヤー状態 { room_slug: { player_id: state } }
# ※ プロセス内メモリなので、ASGIサーバー1プロセス運用が前提(MVP用)
#    views.py からも人数表示のために参照する
ROOMS: dict[str, dict[str, dict]] = {}

SPAWN_RADIUS = 3.0          # 焚火からどれだけ離れた輪に出現するか
DEFAULT_NAME = "旅人"
MAX_NAME_LENGTH = 16
MAX_CHAT_LENGTH = 200
CHAT_INTERVAL_SECONDS = 0.5  # 連続投稿の間隔(これより速い投稿は無視)


class SpaceConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.joined = False
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.group_name = f"space_{self.room_name}"
        self.player_id = uuid.uuid4().hex[:8]
        self.display_name = self._read_name()
        self.last_chat_at = 0.0

        await self.accept()

        occupants = len(ROOMS.get(self.room_name, {}))
        room = await self._get_open_room(occupants)
        if room is None:
            await self.send_json({"type": "room_not_found"})
            await self.close()
            return

        # 焚火を囲む輪の上に、中心を向いて出現させる
        angle = random.uniform(0.0, 2.0 * math.pi)
        state = {
            "id": self.player_id,
            "name": self.display_name,
            "x": SPAWN_RADIUS * math.sin(angle),
            "y": 1.0,
            "z": SPAWN_RADIUS * math.cos(angle),
            "ry": math.degrees(angle) + 180.0,
        }

        players = ROOMS.setdefault(self.room_name, {})
        players[self.player_id] = state
        self.joined = True

        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # 本人には自分のIDと出現位置、すでにいる人の一覧、今の火の状態を送る
        others = [p for pid, p in players.items() if pid != self.player_id]
        heat = fire.effective_heat(room, len(players))
        await self.send_json(
            {"type": "welcome", **state, "players": others, **self._fire_payload(heat)}
        )

        # ほかの人には入室を知らせる
        await self._broadcast({"type": "player_joined", **state})

    async def disconnect(self, code):
        if not self.joined:
            return

        players = ROOMS.get(self.room_name, {})
        players.pop(self.player_id, None)
        remaining = len(players)
        if remaining == 0:
            ROOMS.pop(self.room_name, None)

        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self._broadcast(
            {"type": "player_left", "id": self.player_id, "name": self.display_name}
        )

        # 最後の1人が去ったら、熾火の状態を記録しておく(ここから少しずつ消えていく)
        if remaining == 0:
            await self._bank_embers()

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type")
        if message_type == "move":
            await self._handle_move(content)
        elif message_type == "chat":
            await self._handle_chat(content)

    # --- メッセージ処理 ---

    async def _handle_move(self, content):
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

    async def _handle_chat(self, content):
        text = str(content.get("text", "")).strip()
        if not text:
            return
        text = text[:MAX_CHAT_LENGTH]

        now = time.monotonic()
        if now - self.last_chat_at < CHAT_INTERVAL_SECONDS:
            return
        self.last_chat_at = now

        heat = await self._add_heat(fire.chat_boost(text))

        # チャットは自分にも返す(自分の画面のログにも出すため)
        await self._broadcast(
            {"type": "chat", "id": self.player_id, "name": self.display_name, "text": text},
            include_self=True,
        )
        await self._broadcast({"type": "fire", **self._fire_payload(heat)}, include_self=True)

    # --- 内部処理 ---

    def _read_name(self) -> str:
        query = parse_qs(self.scope.get("query_string", b"").decode("utf-8", errors="ignore"))
        name = query.get("name", [""])[0].strip()[:MAX_NAME_LENGTH]
        return name or DEFAULT_NAME

    @staticmethod
    def _fire_payload(heat: float) -> dict:
        return {
            "heat": round(heat, 4),
            "tau": fire.FIRE_TAU_SECONDS,
            "ember": fire.EMBER_HEAT,
        }

    @database_sync_to_async
    def _get_open_room(self, occupants: int):
        room = SpaceRoom.objects.filter(slug=self.room_name).first()
        if room is None:
            return None
        if fire.is_extinguished(room, occupants):
            room.delete()
            return None
        return room

    @database_sync_to_async
    def _add_heat(self, amount: float) -> float:
        room = SpaceRoom.objects.filter(slug=self.room_name).first()
        if room is None:
            return 0.0

        now = timezone.now()
        occupants = len(ROOMS.get(self.room_name, {}))
        heat = min(1.0, fire.effective_heat(room, occupants, now) + amount)

        room.heat = heat
        room.heat_updated_at = now
        room.save(update_fields=["heat", "heat_updated_at"])
        return heat

    @database_sync_to_async
    def _bank_embers(self):
        room = SpaceRoom.objects.filter(slug=self.room_name).first()
        if room is None:
            return

        now = timezone.now()
        room.heat = max(fire.decayed_heat(room, now), fire.EMBER_HEAT)
        room.heat_updated_at = now
        room.save(update_fields=["heat", "heat_updated_at"])

    async def _broadcast(self, message: dict, include_self: bool = False):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "space.broadcast",
                "message": message,
                "sender": None if include_self else self.player_id,
            },
        )

    async def space_broadcast(self, event):
        sender = event.get("sender")
        if sender is not None and sender == self.player_id:
            return
        await self.send_json(event["message"])