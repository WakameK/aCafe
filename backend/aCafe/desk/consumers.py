import asyncio
import logging
import random
import time
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from . import ai_manager, safety, services
from .models import Message, Room
from .services import FireFullError, cfg

logger = logging.getLogger(__name__)

# ブラウザに伝えるclose code。いずれも「自動で再接続してはいけない」もの
CLOSE_BAD_ID = 4401
CLOSE_FULL = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_OUT = 4410  # 火が消えた / 持ち主が火を消した

# 「死にたい」気持ちを聴くとき、AIが使えなかったときの代わりの一言(KEEPER_GUIDANCE と同じ方針)
KEEPER_FALLBACK = "死にたいほどつらいんだね。ここにいるよ。よかったら、どんなことがあったのか、聞かせてもらえるかな。"

_REPLY_LOCKS = {}
_GUIDE_SENT = {}  # (fire_id, user_id) -> 最後に「聴く側の案内」を出した時刻。出しすぎないための記録


def _reply_lock(room_id):
    # AIの返信が同じ焚火で重ならないようにする(イベントループごとに別のロック)
    return _REPLY_LOCKS.setdefault((id(asyncio.get_running_loop()), room_id), asyncio.Lock())


def _active_characters(room_id):
    room = Room.objects.filter(pk=room_id).first()
    return list(room.active_characters.all()) if room else []


def _room_and_characters(room_id):
    room = Room.objects.filter(pk=room_id).first()
    if room is None:
        return None, []
    return room, list(room.active_characters.all())


def _last_message_content(room_id):
    last = Message.objects.filter(room_id=room_id).order_by("-id").first()
    return last.content if last else ""


class FireConsumer(AsyncJsonWebsocketConsumer):
    """
    1焚火 = 1グループ("fire_<id>")。接続時に ?anon_id=... を渡す(匿名ユーザーのため、Djangoのセッション認証は使わない)。

    - 入る/出るは Presence に記録する。人数のカウンタは持たない。
    - ハートビートで「生きている」ことを記録し続ける。止まったら、workerが輪から外す。
    - 例外で落ちても、切断通知が来なくても、終了時に必ず後始末をする(__call__ の finally)。
    - 発言は見張り(safety)を通ってから、焚火に届く。
    """

    async def connect(self):
        self.entered = False
        self.room_id = int(self.scope["url_route"]["kwargs"]["fire_id"])
        self.group_name = services.group_name(self.room_id)
        self._tasks = set()
        self._holds = {}
        self._hb = None
        self._last_sent_at = 0.0

        qs = dict(
            pair.split("=", 1)
            for pair in self.scope.get("query_string", b"").decode().split("&")
            if "=" in pair
        )
        anon_id = qs.get("anon_id")
        if not services.valid_anon_id(anon_id):
            await self.accept()
            await self.close(code=CLOSE_BAD_ID)
            return

        self.user = await database_sync_to_async(services.get_or_create_guest)(anon_id)

        try:
            result = await database_sync_to_async(services.enter)(
                self.room_id, self.user, self.channel_name
            )
        except Room.DoesNotExist:
            await self.accept()
            await self.close(code=CLOSE_NOT_FOUND)
            return
        except FireFullError:
            await self.accept()
            await self.close(code=CLOSE_FULL)
            return
        self.entered = True

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self._hb = asyncio.ensure_future(self._heartbeat())

        # 同じ人の2つ目の接続(再接続・別タブ)のときは、入室の通知を出さない
        if result.new_member:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.presence",
                    "event": "join",
                    "user": self.user.name,
                    "user_id": self.user.pk,
                    "count": result.count,
                },
            )

    async def __call__(self, scope, receive, send):
        # RedisのTimeoutErrorなどでconsumerが例外終了したときは disconnect() が呼ばれない。
        # その場合でも輪から外れるよう、終了時に必ず後始末する(二重実行は _cleanup 側で防ぐ)
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._cleanup()

    async def disconnect(self, close_code):
        await self._cleanup()

    async def _cleanup(self):
        if not getattr(self, "entered", False):
            return
        self.entered = False  # 二重に後始末しないため

        if self._hb is not None:
            self._hb.cancel()
        for task in list(self._tasks):
            task.cancel()

        # DBの記録を先に消す。Redisが不調でも「輪に残り続ける」ことだけは起きないようにする
        try:
            result = await database_sync_to_async(services.leave)(self.channel_name)
        except Exception:
            logger.warning("leave failed (fire %s)", self.room_id, exc_info=True)
            result = None

        # Redisを使う後始末は失敗しても構わない(最大5秒で諦める)
        try:
            await asyncio.wait_for(self._leave_group(result), timeout=5)
        except Exception:
            logger.warning("leave notice failed (fire %s)", self.room_id, exc_info=True)

    async def _leave_group(self, result):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if result is not None and result.fully_left:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.presence",
                    "event": "leave",
                    "user": result.user.name,
                    "user_id": result.user.pk,
                    "count": result.count,
                },
            )

    async def _heartbeat(self):
        interval = cfg("DESK_HEARTBEAT_SECONDS", 20)
        while True:
            await asyncio.sleep(interval)
            try:
                alive = await database_sync_to_async(services.touch)(
                    self.channel_name, self.room_id, self.user
                )
            except Exception:
                logger.warning("heartbeat failed (fire %s)", self.room_id, exc_info=True)
                continue
            if not alive:
                await self.close(code=CLOSE_OUT)
                return

    def _spawn(self, coro):
        """時間のかかる処理(AIの返事など)を、受信ループを止めずに裏で走らせる。"""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)

        def _done(t):
            self._tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                logger.warning("background task failed (fire %s)", self.room_id, exc_info=t.exception())

        task.add_done_callback(_done)

    # ====================================
    # 受信
    # ====================================

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type", "chat.message")
        if msg_type == "chat.message":
            await self._on_message(content)
        elif msg_type == "chat.resolve_hold":
            await self._on_resolve_hold(content)

    async def _on_message(self, content):
        text = (content.get("message") or "").strip()
        if not text:
            return
        text = text[: cfg("DESK_MAX_MESSAGE_CHARS", 500)]

        now = time.monotonic()
        if now - self._last_sent_at < cfg("DESK_MIN_SEND_INTERVAL", 0.4):  # 連投を防ぐ
            return
        self._last_sent_at = now

        verdict = safety.classify(text)

        if verdict.kind == safety.ATTACK:
            # 他の人には出さずに、本人にだけ「こう言い換えていい?」と聞く
            self._spawn(self._hold(text))
            return

        if verdict.kind == safety.METHOD:
            # 誰にも見せない。本人にだけ、そばにいることと窓口を出す。どこにも保存しない
            await self.send_json({"type": "chat.care", "care": safety.care_payload(safety.METHOD)})
            return

        await self._publish(text)

        if verdict.kind in (safety.IDEATION, safety.IMMINENT):
            await self._care_and_listen(verdict.kind)
        else:
            self._spawn(self._maybe_trigger_ai_reply())

    async def _publish(self, text):
        try:
            message, fire = await database_sync_to_async(services.save_human_message)(
                self.room_id, self.user, text
            )
        except Exception:
            logger.warning("save message failed (fire %s)", self.room_id, exc_info=True)
            await self.send_json({"type": "chat.error", "message": "送れませんでした。もう一度お試しください。"})
            return
        await self.channel_layer.group_send(
            self.group_name, {"type": "chat.message", **services.message_to_dict(message)}
        )
        if fire is not None:
            await self.channel_layer.group_send(self.group_name, {"type": "fire.level", "fire": fire})

    # ====================================
    # 見張り
    # ====================================

    async def _hold(self, text):
        try:
            softened = await database_sync_to_async(ai_manager.suggest_softer_text)(text)
        except Exception:
            logger.warning("soften failed (fire %s)", self.room_id, exc_info=True)
            softened = ""
        softened = softened or safety.mask_attack_words(text)

        hold_id = uuid.uuid4().hex[:8]
        if len(self._holds) >= 5:
            self._holds.pop(next(iter(self._holds)))
        # 元の強い言葉は、どこにも残さない。覚えておくのは、言い換えた文だけ
        self._holds[hold_id] = softened
        await self.send_json(
            {
                "type": "chat.hold",
                "hold_id": hold_id,
                "message": safety.ATTACK_HOLD_TEXT,
                "softened": softened,
            }
        )

    async def _on_resolve_hold(self, content):
        softened = self._holds.pop(content.get("hold_id"), None)
        if softened is None:
            return
        choice = content.get("choice")
        if choice == "softened":
            if safety.classify(softened).kind == safety.ATTACK:
                await self.send_json({"type": "chat.burned"})  # 言い換えでも強いままなら、燃やす
                return
            await self._publish(softened)
            self._spawn(self._maybe_trigger_ai_reply())
        elif choice == "burn":
            # こっそり燃やす: 誰にも見えず、DBにも入れていない
            await self.send_json({"type": "chat.burned"})
        # "cancel"(書き直す)のときは、何もしない

    async def _care_and_listen(self, kind):
        # 本人にだけ、静かな案内
        await self.send_json({"type": "chat.care", "care": safety.care_payload(kind)})

        # 同じ焚火の、ほかの人に「聴く側の案内」(同じ人の分は、30分に1回まで)
        key = (self.room_id, self.user.pk)
        now = time.monotonic()
        if now - _GUIDE_SENT.get(key, -1e9) > 1800:
            _GUIDE_SENT[key] = now
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.guide",
                    "text": safety.listener_guide(kind),
                    "exclude_user_id": self.user.pk,
                },
            )

        self._spawn(self._keeper_reply())

    async def _keeper_reply(self):
        characters = await database_sync_to_async(_active_characters)(self.room_id)
        if not characters:
            # キャラがいなければ、すぐに1人来てもらう(聴く役がいない状態にしないため)
            character, borrowed_from = await database_sync_to_async(services.acquire_character)(self.room_id)
            if character is None:
                return
            if borrowed_from:
                await self.channel_layer.group_send(
                    services.group_name(borrowed_from),
                    {"type": "chat.presence", "event": "ai_leave", "user": character.name, "user_id": None},
                )
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "chat.presence", "event": "ai_join", "user": character.name, "user_id": None},
            )
            characters = [character]
        await self._ai_reply(
            [characters[0]], guidance=ai_manager.KEEPER_GUIDANCE, fallback=KEEPER_FALLBACK
        )

    # ====================================
    # AIの返信
    # ====================================

    async def _maybe_trigger_ai_reply(self):
        room, characters = await database_sync_to_async(_room_and_characters)(self.room_id)
        if room is None or not characters:
            return
        if _reply_lock(self.room_id).locked():
            return  # すでに返事を考えているキャラがいる

        if room.mode == Room.MODE_QUIET:
            # 静かモードでは、名前を呼ばれたときだけ反応する
            last = await database_sync_to_async(_last_message_content)(self.room_id)
            responders = [c for c in characters if c.name in last]
            if not responders:
                return
        else:
            responders = characters
        await self._ai_reply(responders)

    async def _ai_reply(self, responders, guidance=None, fallback=None):
        async with _reply_lock(self.room_id):
            recent = await database_sync_to_async(services.recent_text)(self.room_id)
            for character in responders:
                # 衝動的に即返す/一拍置くを疑似的なランダム遅延で表現する
                await asyncio.sleep(random.uniform(0.5, 2.5))
                try:
                    text = await database_sync_to_async(ai_manager.generate_character_reply)(
                        character, recent, guidance
                    )
                except Exception:
                    # Ollama停止など。キャラが「今日は調子が悪くて話せない」だけで、接続は落とさない
                    logger.warning("AI reply failed for %s", character.name, exc_info=True)
                    text = fallback
                text = (text or "").strip()
                if not text:
                    continue
                message = await database_sync_to_async(services.save_ai_message)(
                    self.room_id, character, text
                )
                await self.channel_layer.group_send(
                    self.group_name, {"type": "chat.message", **services.message_to_dict(message)}
                )
                recent += f"\n{character.name}: {text}"

    # ====================================
    # グループイベント → クライアント送信
    # ====================================

    async def chat_message(self, event):
        await self.send_json(
            {
                "type": "chat.message",
                "sender_type": event["sender_type"],
                "sender_name": event["sender_name"],
                "sender_user_id": event.get("sender_user_id"),
                "message": event["message"],
                "message_id": event.get("id"),
                "created_at": event.get("created_at"),
            }
        )

    async def chat_presence(self, event):
        await self.send_json(
            {
                "type": "chat.presence",
                "event": event["event"],
                "user": event["user"],
                # 受け取った側が「これは自分の入退室か」を判定できるようにする(AIはNone)
                "user_id": event.get("user_id"),
                "count": event.get("count"),
            }
        )

    async def chat_gift(self, event):
        await self.send_json({"type": "chat.gift", "gift": event["gift"]})

    async def chat_guide(self, event):
        if event.get("exclude_user_id") == self.user.pk:
            return
        await self.send_json({"type": "chat.guide", "text": event["text"]})

    async def fire_level(self, event):
        await self.send_json({"type": "fire.level", "fire": event["fire"]})

    async def fire_closing(self, event):
        await self.send_json({"type": "fire.closing"})

    async def fire_updated(self, event):
        await self.send_json(
            {
                "type": "fire.updated",
                "name": event["name"],
                "topic": event["topic"],
                "capacity": event["capacity"],
                "public_note": event["public_note"],
            }
        )

    async def fire_out(self, event):
        await self.send_json({"type": "fire.out"})
        await self.close(code=CLOSE_OUT)

    async def note_draft(self, event):
        # 外向けのひとことの下書きは、持ち主にだけ見せる
        if event.get("owner_id") == self.user.pk:
            await self.send_json({"type": "note.draft", "draft": event["draft"]})
