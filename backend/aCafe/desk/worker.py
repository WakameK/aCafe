"""
焚火の世話をする処理。desk_worker コマンドが、一定間隔で run_tick() を呼ぶ。

1回(tick)でやること:
  1. 更新が止まった接続を輪から外す(ブラウザを閉じた・回線が切れた・サーバーが落ちた)
  2. 焚火を見て回る
       - 火が消えた焚火は、焚火ごと(発言も)消す
       - 火が小さくなってきたら「そろそろ終いにしようか」と声をかける
       - 誰もいなくなった焚火から、AIキャラを帰す
       - 輪の様子(新しい人を待っていそうか・内輪か)を、発言の数から決める
       - ひとりで火にあたっている人のところへ、しばらくしてからAIキャラが来る(待った時間が長い順)
       - AIだけの焚火で、AIが出入りしたり、雑談したりする
  3. 持ち主にだけ見せる「外向けのひとこと」の下書きを作る
  4. AIの焚火に溜まった古い発言を消す
"""
import logging
import random
from datetime import timedelta

from django.utils import timezone

from . import ai_manager, services
from .models import Message, Room
from .services import broadcast, cfg

logger = logging.getLogger(__name__)

CLOSING_LINES = [
    "火が小さくなってきたね。今日はこのくらいで終いにしようか。また会えたらいいね。",
    "そろそろ火が落ちそうだね。話してくれてありがとう。また、どこかで。",
    "火が眠そうだ。今日はここまでにしようか。またここで会えたらうれしいな。",
]

AI_GIFT_LINES = [
    "よかったら、どうぞ。",
    "お邪魔します。あったかいの、置いておくね。",
    "ひとりなら、ご一緒していいかな。",
]


def run_tick(now=None):
    """1回分の世話。途中の処理が失敗しても、ほかの処理は続ける。"""
    now = now or timezone.now()
    for step in (_purge_stale, _tend_fires, _draft_notes, _prune):
        try:
            step(now)
        except Exception:
            logger.warning("desk tick step failed: %s", step.__name__, exc_info=True)


# ====================================
# 1. 止まった接続を外す
# ====================================

def _purge_stale(now):
    for result in services.purge_stale(now):
        broadcast(
            result.room_id,
            {
                "type": "chat.presence",
                "event": "leave",
                "user": result.user.name,
                "user_id": result.user.pk,
                "count": result.count,
            },
        )


# ====================================
# 2. 焚火を見て回る
# ====================================

def _tend_fires(now):
    rooms = list(
        Room.objects.exclude(kind=Room.KIND_LEGACY).prefetch_related("active_characters").order_by("id")
    )
    lonely = []

    for room in rooms:
        hc = services.human_count(room.pk, now)
        characters = list(room.active_characters.all())

        # 火が消えた → 焚火ごと消える
        if services.is_burnt_out(room, now):
            broadcast(room.pk, {"type": "fire.out"})
            services.extinguish(room.pk)
            continue

        if room.kind == Room.KIND_USER:
            if hc == 0 and characters:
                services.release_characters(room.pk)  # 誰もいなくなったら、キャラは自分の生活に戻る
                characters = []
            if hc >= 1:
                _maybe_announce_closing(room, characters, now)

        welcome = services.compute_welcome(room, hc, now)
        if welcome != room.welcome:
            Room.objects.filter(pk=room.pk).update(welcome=welcome)

        if hc == 1 and not characters:
            lonely.append(room)
        elif room.ai_join_after is not None:
            Room.objects.filter(pk=room.pk).update(ai_join_after=None)

        if room.kind == Room.KIND_AMBIENT and hc == 0:
            _ambient_step(room, characters, now)

    _lonely_joins(lonely, now)


def _maybe_announce_closing(room, characters, now):
    level = services.fire_level_now(room, now)
    if room.kind != Room.KIND_USER or room.closing_announced:
        return
    if level >= cfg("DESK_FIRE_CLOSING_LEVEL", 0.2):
        return

    Room.objects.filter(pk=room.pk).update(closing_announced=True)
    broadcast(room.pk, {"type": "fire.closing"})
    if characters:
        speaker = random.choice(characters)
        message = services.save_ai_message(room.pk, speaker, random.choice(CLOSING_LINES))
        broadcast(room.pk, {"type": "chat.message", **services.message_to_dict(message)})


# ---- ひとりで火にあたっている人のところへ、AIキャラが来る ----

def _lonely_joins(lonely, now):
    low, high = cfg("DESK_LONELY_JOIN_SECONDS", (30, 60))
    ready = []
    for room in lonely:
        if room.ai_join_after is None:
            room.ai_join_after = now + timedelta(seconds=random.uniform(low, high))
            Room.objects.filter(pk=room.pk).update(ai_join_after=room.ai_join_after)
        if room.ai_join_after <= now:
            ready.append(room)

    # 待った時間が長い順。AIの返事は時間がかかるので、1回で動かす数に上限を付ける
    ready.sort(key=lambda r: r.ai_join_after)
    for room in ready[: cfg("DESK_MAX_JOINS_PER_TICK", 2)]:
        _join_lonely_fire(room, now)


def _join_lonely_fire(room, now):
    # 動く直前に、まだ一人きりか確かめる(待っている間に、誰かが来た・出ていったかもしれない)
    if services.human_count(room.pk, now) != 1 or room.active_characters.exists():
        Room.objects.filter(pk=room.pk).update(ai_join_after=None)
        return

    character, borrowed_from = services.acquire_character(room.pk)
    if character is None:
        # 来られるキャラがいない。少しあとでもう一度
        Room.objects.filter(pk=room.pk).update(ai_join_after=now + timedelta(seconds=60))
        return
    Room.objects.filter(pk=room.pk).update(ai_join_after=None)

    if borrowed_from:
        broadcast(
            borrowed_from,
            {"type": "chat.presence", "event": "ai_leave", "user": character.name, "user_id": None},
        )
    broadcast(
        room.pk,
        {"type": "chat.presence", "event": "ai_join", "user": character.name, "user_id": None},
    )

    # 来たキャラは、まずコーヒーを置いてくれる
    gift, fire = services.give_ai_gift(room.pk, character, "コーヒー", random.choice(AI_GIFT_LINES))
    broadcast(room.pk, {"type": "chat.gift", "gift": gift})
    if fire is not None:
        broadcast(room.pk, {"type": "fire.level", "fire": fire})

    try:
        text = ai_manager.generate_character_reply(
            character, services.recent_text(room.pk), timeout=cfg("DESK_WORKER_AI_TIMEOUT", 30)
        )
    except Exception:
        logger.warning("greeting failed for %s", character.name, exc_info=True)
        return  # AIが使えなくても、来てコーヒーを置いたところまでは成立している
    text = (text or "").strip()
    if text:
        message = services.save_ai_message(room.pk, character, text)
        broadcast(room.pk, {"type": "chat.message", **services.message_to_dict(message)})


# ---- AIだけの焚火 ----

def _ambient_step(room, characters, now):
    """AIだけの焚火で、キャラが入ったり、雑談したり、帰ったりする。動くのは数分に1回くらい。"""
    if room.ambient_next_at is not None and room.ambient_next_at > now:
        return

    target = cfg("DESK_AMBIENT_CHARACTERS", 2)
    if len(characters) < target:
        for character in ai_manager.pick_characters_for_room(room, count=target - len(characters)):
            room.active_characters.add(character)
            broadcast(
                room.pk,
                {"type": "chat.presence", "event": "ai_join", "user": character.name, "user_id": None},
            )
    elif random.random() < 0.2:
        leaver = random.choice(characters)
        room.active_characters.remove(leaver)
        broadcast(
            room.pk,
            {"type": "chat.presence", "event": "ai_leave", "user": leaver.name, "user_id": None},
        )
    elif len(characters) >= 2:
        a, b = random.sample(characters, 2)
        try:
            exchange = ai_manager.generate_ambient_exchange(
                a, b, room, turns=random.randint(1, 2), timeout=cfg("DESK_WORKER_AI_TIMEOUT", 30)
            )
        except Exception:
            logger.warning("ambient chat failed (fire %s)", room.pk, exc_info=True)
            exchange = []
        for speaker, line in exchange:
            message = services.save_ai_message(room.pk, speaker, line)
            broadcast(room.pk, {"type": "chat.message", **services.message_to_dict(message)})

    low, high = cfg("DESK_AMBIENT_INTERVAL_SECONDS", (90, 240))
    Room.objects.filter(pk=room.pk).update(
        ambient_next_at=now + timedelta(seconds=random.uniform(low, high))
    )


# ====================================
# 3. 外向けのひとこと(下書き)
# ====================================

def _draft_notes(now):
    """
    話題が変わってきた焚火に、「外向けのひとこと」の下書きを作って、持ち主にだけ見せる。
    持ち主が承認するまで、外(一覧)には出ない。AIが重いので、1回の tick で1つだけ。
    """
    min_messages = cfg("DESK_NOTE_MIN_MESSAGES", 4)
    min_seconds = cfg("DESK_NOTE_MIN_SECONDS", 180)

    for room in Room.objects.filter(kind=Room.KIND_USER, owner__isnull=False).order_by("id"):
        if services.human_count(room.pk, now) == 0:
            continue
        if not services.active_presences(room.pk, now).filter(user_id=room.owner_id).exists():
            continue  # 持ち主がいないときは作らない(見せる相手がいない)
        if room.note_draft_at and (now - room.note_draft_at).total_seconds() < min_seconds:
            continue
        since = room.note_draft_at or room.created_at
        if Message.objects.filter(room=room, created_at__gt=since).count() < min_messages:
            continue

        # 失敗しても時刻は進めて、AIが止まっている間に毎回待たされないようにする
        Room.objects.filter(pk=room.pk).update(note_draft_at=now)
        try:
            draft = ai_manager.draft_public_note(
                services.recent_text(room.pk), timeout=cfg("DESK_WORKER_AI_TIMEOUT", 30)
            )
        except Exception:
            logger.warning("note draft failed (fire %s)", room.pk, exc_info=True)
            return
        if draft:
            Room.objects.filter(pk=room.pk).update(note_draft=draft)
            broadcast(room.pk, {"type": "note.draft", "owner_id": room.owner_id, "draft": draft})
        return


# ====================================
# 4. 後片付け
# ====================================

def _prune(now):
    services.prune_ambient_messages(keep=cfg("DESK_AMBIENT_KEEP_MESSAGES", 50))
