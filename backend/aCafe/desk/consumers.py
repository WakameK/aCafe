import asyncio
import logging
import random

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.db import transaction

from sosuke.models import Users
from .models import Room, Message
from . import ai_manager, seats

logger = logging.getLogger(__name__)


class RoomConsumer(AsyncJsonWebsocketConsumer):
    """
    1部屋 = 1グループ("room_<id>")。
    クライアントは接続時に ?anon_id=... をクエリ文字列で渡す想定
    (匿名ユーザーのため、Django標準のセッション認証は使わない)。
    """

    async def connect(self):
        self.room_id = int(self.scope["url_route"]["kwargs"]["room_id"])
        self.group_name = f"room_{self.room_id}"

        qs = dict(
            pair.split("=", 1)
            for pair in (self.scope.get("query_string", b"").decode().split("&"))
            if "=" in pair
        )
        self.anon_id = qs.get("anon_id")

        room = await self._get_room()
        if room is None:
            await self.close(code=4404)
            return

        self.user = await self._get_or_create_user(self.anon_id)

        # 席の定員を超えていたら入れない(座席に紐づくチャット空間のみ)
        if not await self._try_enter(self.room_id):
            await self.close(code=4403)
            return
        self.entered = True

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(
            self.group_name,
            {"type": "chat.presence", "event": "join", "user": self.user.name},
        )

        # 一人で座っているのにAIキャラもいない場合、しばらくしてからAIキャラが入ってくる
        should_schedule = await self._claim_ai_join_if_needed(self.room_id)
        if should_schedule:
            asyncio.ensure_future(self._delayed_ai_join(self.room_id))

    async def disconnect(self, close_code):
        if getattr(self, "entered", False):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            await database_sync_to_async(seats.leave)(self.room_id, self.channel_name)
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "chat.presence", "event": "leave", "user": self.user.name},
            )

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type", "chat.message")

        if msg_type == "ping":
            # クライアントの生存確認。在席を更新する
            await database_sync_to_async(seats.touch)(self.room_id, self.channel_name)
            return

        if msg_type == "chat.message":
            text = (content.get("message") or "").strip()
            if not text:
                return
            message = await self._save_message(self.room_id, self.user, text)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.message",
                    "sender_type": "human",
                    "sender_name": self.user.name,
                    "message": text,
                    "message_id": message.id,
                },
            )
            await self._maybe_trigger_ai_reply(self.room_id)

    # --- グループイベント→クライアント送信のハンドラ群 ---

    async def chat_message(self, event):
        await self.send_json(
            {
                "type": "chat.message",
                "sender_type": event["sender_type"],
                "sender_name": event["sender_name"],
                "message": event["message"],
                "message_id": event.get("message_id"),
            }
        )

    async def chat_presence(self, event):
        await self.send_json(
            {"type": "chat.presence", "event": event["event"], "user": event["user"]}
        )

    async def chat_gift(self, event):
        await self.send_json({"type": "chat.gift", "gift": event["gift"]})

    async def chat_atmosphere(self, event):
        await self.send_json({"type": "chat.atmosphere", "summary": event["summary"]})

    # --- AI入室のスケジューリング ---

    async def _delayed_ai_join(self, room_id):
        low, high = getattr(settings, "DESK_LONELY_JOIN_SECONDS", (30, 60))
        await asyncio.sleep(random.uniform(low, high))

        # まだ一人きりのときだけ入ってくる(誰かと相席になっていたり、席を離れていたら何もしない)
        if not await self._room_has_lone_human(room_id):
            await self._release_ai_join_flag(room_id)
            return

        room = await self._get_room(room_id)
        character = await self._pick_and_attach_character(room)
        if character is None:
            return  # 使えるキャラが残っていない

        await self.channel_layer.group_send(
            f"room_{room_id}",
            {
                "type": "chat.presence",
                "event": "ai_join",
                "user": character.name,
            },
        )
        await self._ai_reply(room_id, [character])

    # --- AIの返信トリガー ---

    async def _maybe_trigger_ai_reply(self, room_id):
        room = await self._get_room(room_id)
        if room is None:
            return

        active_characters = await self._get_active_characters(room)
        if not active_characters:
            return

        if room.mode == Room.MODE_QUIET:
            # 静かモードでは、明示的に呼びかけられた時だけ反応する(簡易実装: 名前が含まれるか)
            last_message = await self._get_last_message(room_id)
            if last_message is None:
                return
            called = [c for c in active_characters if c.name in last_message.content]
            if not called:
                return
            responders = called
        else:
            # 話したいモードでは、参加中のキャラ全員がそれぞれ反応候補になる
            responders = active_characters

        await self._ai_reply(room_id, responders)

    async def _ai_reply(self, room_id, responders):
        recent_text = await self._get_recent_messages_text(room_id)

        for character in responders:
            # 衝動的に即返す/一拍置くを疑似的なランダム遅延で表現する
            await asyncio.sleep(random.uniform(0.5, 2.5))
            try:
                reply_text = await database_sync_to_async(ai_manager.generate_character_reply)(
                    character, recent_text
                )
            except Exception:
                # Ollama停止など。キャラが「今日は調子が悪くて話せない」だけで、接続は落とさない
                logger.warning("AI reply failed for %s", character.name, exc_info=True)
                continue
            reply_text = (reply_text or "").strip()
            if not reply_text:
                continue
            message = await self._save_ai_message(room_id, character, reply_text)
            await self.channel_layer.group_send(
                f"room_{room_id}",
                {
                    "type": "chat.message",
                    "sender_type": "ai",
                    "sender_name": character.name,
                    "message": reply_text,
                    "message_id": message.id,
                },
            )
            recent_text += f"\n{character.name}: {reply_text}"

    # --- DBアクセス(同期ORM呼び出しをasyncから使うためのラッパー) ---

    @database_sync_to_async
    def _get_room(self, room_id=None):
        try:
            return Room.objects.get(pk=room_id or self.room_id)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def _get_or_create_user(self, anon_id):
        anon_id = anon_id or "anonymous"
        user, _ = Users.objects.get_or_create(
            anon_id=anon_id, defaults={"name": f"ゲスト-{anon_id[:6]}"}
        )
        return user

    @database_sync_to_async
    def _claim_ai_join_if_needed(self, room_id):
        with transaction.atomic():
            room = Room.objects.select_for_update().get(pk=room_id)
            if seats.live_count(room) != 1 or room.ai_join_scheduled or room.active_characters.exists():
                return False
            room.ai_join_scheduled = True
            room.save(update_fields=["ai_join_scheduled"])
            return True

    @database_sync_to_async
    def _release_ai_join_flag(self, room_id):
        Room.objects.filter(pk=room_id).update(ai_join_scheduled=False)

    @database_sync_to_async
    def _try_enter(self, room_id):
        """在席に加わる。座席に紐づく部屋で定員いっぱいなら False。"""
        return seats.enter(room_id, self.channel_name)

    @database_sync_to_async
    def _room_has_lone_human(self, room_id):
        room = Room.objects.filter(pk=room_id).first()
        return bool(room and seats.live_count(room) == 1)

    @database_sync_to_async
    def _pick_and_attach_character(self, room):
        candidates = ai_manager.pick_characters_for_room(room, count=1)
        if not candidates:
            return None
        character = candidates[0]
        room.active_characters.add(character)
        room.ai_join_scheduled = False
        room.save(update_fields=["ai_join_scheduled"])
        return character

    @database_sync_to_async
    def _get_active_characters(self, room):
        return list(room.active_characters.all())

    @database_sync_to_async
    def _get_last_message(self, room_id):
        return Message.objects.filter(room_id=room_id).order_by("-created_at").first()

    @database_sync_to_async
    def _get_recent_messages_text(self, room_id, limit=20):
        messages = Message.objects.filter(room_id=room_id).order_by("-created_at")[:limit]
        char_by_id = {c.character_id: c.name for c in ai_manager.Character.objects.all()}
        return ai_manager.format_recent_messages(reversed(list(messages)), char_by_id, limit=limit)

    @database_sync_to_async
    def _save_message(self, room_id, user, text):
        return Message.objects.create(
            room_id=room_id, user=user, sender_type=Message.SENDER_HUMAN, content=text
        )

    @database_sync_to_async
    def _save_ai_message(self, room_id, character, text):
        return Message.objects.create(
            room_id=room_id,
            character=character,
            sender_type=Message.SENDER_AI,
            content=text,
        )
