"""
焚火(desk)のドメインロジック。HTTP view / WebSocket consumer / worker の3つから共通で使う(すべて同期)。

- 火: fire_level_now / feed_fire / extinguish(火が消えたら焚火ごと消える)
- 輪: enter / leave / touch / purge_stale(Presence から人数を数える)
- 発言・薪: save_human_message / give_gift ほか
- 一覧: list_fires / fire_to_dict
- AIキャラの出入り: acquire_character / release_characters
"""
import logging
import re
from collections import namedtuple
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Q, When
from django.utils import timezone

from sosuke.models import Users
from . import ai_manager
from .models import DrinkGift, Message, Presence, Room

logger = logging.getLogger(__name__)


def cfg(name, default):
    """settings.py に書けば上書きできる設定値。"""
    return getattr(settings, name, default)


class FireFullError(Exception):
    """輪がいっぱいで入れない。"""


class FireError(Exception):
    """入力が正しくない・上限を超えているなど、利用者に伝えるべきエラー。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


EnterResult = namedtuple("EnterResult", "room new_member count")
LeaveResult = namedtuple("LeaveResult", "room_id user fully_left count")


# ====================================
# グループ配信
# ====================================

def group_name(room_id):
    return f"fire_{room_id}"


def broadcast(room_id, payload):
    """焚火にいる全員にイベントを送る(同期コードから使う)。失敗しても処理は止めない。"""
    try:
        async_to_sync(get_channel_layer().group_send)(group_name(room_id), payload)
    except Exception:
        logger.warning("broadcast failed (fire %s)", room_id, exc_info=True)


# ====================================
# ゲスト(匿名ユーザー)
# ====================================

ANON_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,50}$")


def valid_anon_id(anon_id):
    return bool(anon_id) and bool(ANON_ID_RE.match(anon_id))


def get_or_create_guest(anon_id):
    user = Users.objects.filter(anon_id=anon_id).order_by("pk").first()
    if user is None:
        user = Users.objects.create(anon_id=anon_id, name=f"ゲスト-{anon_id[:6]}")
    return user


MAX_DISPLAY_NAME = 20


def set_display_name(user, raw):
    """プロフィールで決めた名前を反映する。空・長すぎる・制御文字は整えて、決められなければ変えない。"""
    if not isinstance(raw, str):
        return user
    name = "".join(ch for ch in raw if ch.isprintable()).strip()[:MAX_DISPLAY_NAME]
    if name and name != user.name:
        user.name = name
        user.save(update_fields=["name"])
    return user


# ====================================
# 火
# ====================================

def fire_level_now(room, now=None):
    """いまの火の大きさ(0〜1)。保存した値から、時間がたった分だけ小さくする。"""
    now = now or timezone.now()
    minutes = max(0.0, (now - room.fire_updated_at).total_seconds() / 60.0)
    level = max(0.0, room.fire_level - cfg("DESK_FIRE_DECAY_PER_MIN", 0.02) * minutes)
    if room.kind == Room.KIND_AMBIENT:
        level = max(level, 0.5)  # AIたちの焚火は消えない
    return min(1.0, level)


def fire_stage(level):
    if level >= 0.7:
        return "high", "大きく燃えている"
    if level >= 0.4:
        return "mid", "ゆらゆら燃えている"
    if level >= 0.15:
        return "low", "小さくなってきた"
    return "ember", "種火になった"


def fire_dict(room, now=None):
    level = fire_level_now(room, now)
    stage, label = fire_stage(level)
    return {"level": round(level, 3), "stage": stage, "label": label}


def is_burnt_out(room, now=None):
    return room.kind == Room.KIND_USER and fire_level_now(room, now) <= 0.005


def feed_fire(room_id, amount, now=None):
    """火に薪をくべる(大きくする)。焚火が無ければ None。返り値は fire_dict。"""
    now = now or timezone.now()
    try:
        with transaction.atomic():
            room = Room.objects.select_for_update().get(pk=room_id)
            level = min(1.0, fire_level_now(room, now) + amount)
            room.fire_level = level
            room.fire_updated_at = now
            room.last_active_at = now
            if level > cfg("DESK_FIRE_CLOSING_LEVEL", 0.2) + 0.1:
                room.closing_announced = False
            room.save(update_fields=["fire_level", "fire_updated_at", "last_active_at", "closing_announced"])
    except Room.DoesNotExist:
        return None
    return fire_dict(room, now)


def extinguish(room_id):
    """火を消す。焚火も、そこでの発言・薪・接続の記録も、まとめて消える。"""
    deleted, _ = Room.objects.filter(pk=room_id).exclude(kind=Room.KIND_LEGACY).delete()
    return deleted > 0


# ====================================
# 輪(Presence)
# ====================================

def presence_ttl():
    return timedelta(seconds=cfg("DESK_PRESENCE_TTL_SECONDS", 60))


def active_presences(room_id, now=None):
    now = now or timezone.now()
    return Presence.objects.filter(room_id=room_id, last_seen__gte=now - presence_ttl())


def human_count(room_id, now=None):
    return active_presences(room_id, now).values("user_id").distinct().count()


def enter(room_id, user, channel_name, now=None):
    """輪に入る。いっぱいなら FireFullError、焚火が無ければ Room.DoesNotExist。"""
    now = now or timezone.now()
    with transaction.atomic():
        room = Room.objects.select_for_update().exclude(kind=Room.KIND_LEGACY).get(pk=room_id)
        ids = set(active_presences(room_id, now).values_list("user_id", flat=True))
        already = user.pk in ids
        if not already and len(ids) >= room.capacity:
            raise FireFullError(room_id)
        Presence.objects.create(room=room, user=user, channel_name=channel_name, last_seen=now)
        Room.objects.filter(pk=room_id).update(last_active_at=now)
    new_member = not already
    if new_member:
        feed_fire(room_id, cfg("DESK_FIRE_FEED_JOIN", 0.05), now)
    return EnterResult(room, new_member, len(ids) + (1 if new_member else 0))


def leave(channel_name, now=None):
    """接続を1つ外す。記録が無ければ None。同じ人の別の接続が残っていれば fully_left=False。"""
    now = now or timezone.now()
    presence = Presence.objects.select_related("user").filter(channel_name=channel_name).first()
    if presence is None:
        return None
    room_id, user = presence.room_id, presence.user
    presence.delete()
    still_here = active_presences(room_id, now).filter(user_id=user.pk).exists()
    Room.objects.filter(pk=room_id).update(last_active_at=now)
    return LeaveResult(room_id, user, not still_here, human_count(room_id, now))


def touch(channel_name, room_id, user, now=None):
    """生きていることを記録する(ハートビート)。記録が消えていたら入り直す。続けられなければ False。"""
    now = now or timezone.now()
    if Presence.objects.filter(channel_name=channel_name).update(last_seen=now):
        return True
    try:
        enter(room_id, user, channel_name, now)
        return True
    except (FireFullError, Room.DoesNotExist):
        return False


def purge_stale(now=None):
    """
    更新が止まった接続(ブラウザを閉じた・回線が切れた・サーバーが落ちたなど)を片付ける。
    その人の最後の接続だった場合のみ、「席を立った」通知を出すための LeaveResult を返す。
    """
    now = now or timezone.now()
    stale = list(Presence.objects.filter(last_seen__lt=now - presence_ttl()).select_related("user"))
    if not stale:
        return []
    Presence.objects.filter(pk__in=[p.pk for p in stale]).delete()
    results, seen = [], set()
    for p in stale:
        key = (p.room_id, p.user_id)
        if key in seen:
            continue
        seen.add(key)
        if not active_presences(p.room_id, now).filter(user_id=p.user_id).exists():
            results.append(LeaveResult(p.room_id, p.user, True, human_count(p.room_id, now)))
    return results


# ====================================
# 発言
# ====================================

def message_to_dict(m):
    if m.sender_type == Message.SENDER_AI:
        name = m.character.name if m.character_id else "AI"
        user_id = None
    else:
        name = m.user.name if m.user_id else "unknown"
        user_id = m.user_id
    return {
        "id": m.id,
        "sender_type": m.sender_type,
        "sender_name": name,
        "sender_user_id": user_id,
        "message": m.content,
        "created_at": m.created_at.isoformat(),
    }


def save_human_message(room_id, user, text):
    message = Message.objects.create(
        room_id=room_id, user=user, sender_type=Message.SENDER_HUMAN, content=text
    )
    fire = feed_fire(room_id, cfg("DESK_FIRE_FEED_MESSAGE", 0.08))
    return message, fire


def save_ai_message(room_id, character, text):
    return Message.objects.create(
        room_id=room_id, character=character, sender_type=Message.SENDER_AI, content=text
    )


def recent_messages(room_id, limit=30, before=None, after=None):
    """古い順の発言。after を渡すと、それより新しい発言(再接続のときの取りこぼし用)。"""
    qs = Message.objects.filter(room_id=room_id).select_related("user", "character")
    if after is not None:
        rows = list(qs.filter(id__gt=after).order_by("id")[:limit])
    else:
        if before is not None:
            qs = qs.filter(id__lt=before)
        rows = list(qs.order_by("-id")[:limit])
        rows.reverse()
    return [message_to_dict(m) for m in rows]


def recent_text(room_id, limit=20):
    """AIに渡すための、直近の会話のテキスト。"""
    rows = list(
        Message.objects.filter(room_id=room_id)
        .select_related("user", "character")
        .order_by("-id")[:limit]
    )
    rows.reverse()
    return ai_manager.format_recent_messages(rows, limit=limit)


def prune_ambient_messages(keep=50):
    """AIたちの焚火は消えないので、発言が溜まり続けないよう、新しい分だけ残す。"""
    for room in Room.objects.filter(kind=Room.KIND_AMBIENT):
        old_ids = list(
            Message.objects.filter(room=room).order_by("-id").values_list("id", flat=True)[keep:]
        )
        if old_ids:
            Message.objects.filter(id__in=old_ids).delete()


# ====================================
# 薪(コーヒーなどを置く)
# ====================================

def gift_items():
    return list(cfg("DESK_GIFT_ITEMS", ["薪", "コーヒー", "お茶", "毛布"]))


def gift_to_dict(gift):
    if gift.from_character_id:
        name, user_id = gift.from_character.name, None
    else:
        name, user_id = gift.from_user.name, gift.from_user_id
    return {
        "id": gift.id,
        "from": name,
        "from_user_id": user_id,
        "item": gift.item_name,
        "message": gift.message,
    }


def give_gift(room_id, user, item, message=""):
    gift = DrinkGift.objects.create(room_id=room_id, from_user=user, item_name=item, message=message)
    fire = feed_fire(room_id, cfg("DESK_FIRE_FEED_GIFT", 0.15))
    return gift_to_dict(gift), fire


def give_ai_gift(room_id, character, item, message=""):
    gift = DrinkGift.objects.create(
        room_id=room_id, from_character=character, item_name=item, message=message
    )
    fire = feed_fire(room_id, cfg("DESK_FIRE_FEED_GIFT", 0.15))
    return gift_to_dict(gift), fire


def recently_gave(room_id, user, seconds=5, now=None):
    now = now or timezone.now()
    return DrinkGift.objects.filter(
        room_id=room_id, from_user=user, created_at__gte=now - timedelta(seconds=seconds)
    ).exists()


# ====================================
# 焚火を起こす・変える
# ====================================

def _parse_capacity(value):
    low, high = 2, cfg("DESK_MAX_CAPACITY", 12)
    try:
        capacity = int(value)
    except (TypeError, ValueError):
        raise FireError(f"輪の人数は{low}〜{high}で指定してください。")
    if not low <= capacity <= high:
        raise FireError(f"輪の人数は{low}〜{high}で指定してください。")
    return capacity


def _clean_name(value):
    name = (value or "").strip()
    if not 1 <= len(name) <= 30:
        raise FireError("焚火の名前は1〜30文字にしてください。")
    return name


def create_fire(owner, name, topic="", capacity=6):
    name = _clean_name(name)
    capacity = _parse_capacity(capacity)
    limit = cfg("DESK_MAX_FIRES_PER_USER", 3)
    if Room.objects.filter(owner=owner, kind=Room.KIND_USER).count() >= limit:
        raise FireError(f"起こせる焚火は同時に{limit}つまでです。")
    return Room.objects.create(
        name=name,
        topic=(topic or "").strip()[:60],
        kind=Room.KIND_USER,
        owner=owner,
        capacity=capacity,
        fire_level=cfg("DESK_FIRE_START_LEVEL", 0.6),
    )


def update_fire(room, name=None, topic=None, capacity=None, public_note=None):
    """持ち主が焚火を変える。輪の人数を、いまいる人数より少なくしても、いる人は追い出さない(新しく入れないだけ)。"""
    fields = []
    if name is not None:
        room.name = _clean_name(name)
        fields.append("name")
    if topic is not None:
        room.topic = topic.strip()[:60]
        fields.append("topic")
    if capacity is not None:
        room.capacity = _parse_capacity(capacity)
        fields.append("capacity")
    if public_note is not None:
        room.public_note = public_note.strip()[:120]
        fields.append("public_note")
        if public_note.strip():
            room.note_draft = ""
            fields.append("note_draft")
    if fields:
        room.save(update_fields=fields)
    return room


# ====================================
# 一覧
# ====================================

WELCOME_TEXT = {
    "waiting": "輪に空きがあります。新しい人を待っているみたい",
    "insiders": "いつもの顔ぶれで盛り上がっているみたい",
    "quiet": "静かに燃えています",
}


def welcome_text(room, hc):
    if hc >= room.capacity:
        return "いまは輪がいっぱいです"
    if hc == 0:
        if room.kind == Room.KIND_AMBIENT and room.active_characters.exists():
            return "AIたちがのんびり過ごしています"
        return "誰もいません。火だけが燃えています"
    if hc == 1:
        return "ひとりで火にあたっています。誰かを待っているみたい"
    return WELCOME_TEXT.get(room.welcome, WELCOME_TEXT["quiet"])


def compute_welcome(room, hc, now=None):
    """輪の様子を、発言の数から決める(workerが定期的に呼ぶ)。AIの印象ではなく、数字で測る。"""
    now = now or timezone.now()
    if hc < 2:
        return ""
    human = Message.objects.filter(room=room, sender_type=Message.SENDER_HUMAN)
    if not human.filter(created_at__gte=now - timedelta(minutes=10)).exists():
        return "quiet"
    counts = list(
        human.filter(created_at__gte=now - timedelta(minutes=30))
        .values("user_id")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    total = sum(c["n"] for c in counts)
    if hc >= 3 and total >= 8 and sum(c["n"] for c in counts[:2]) / total >= 0.8:
        return "insiders"
    if hc < room.capacity:
        return "waiting"
    return "quiet"


def fire_to_dict(room, hc, viewer=None, now=None):
    return {
        "id": room.id,
        "name": room.name,
        "topic": room.topic,
        "kind": room.kind,
        "capacity": room.capacity,
        "human_count": hc,
        "is_full": hc >= room.capacity,
        "characters": [c.name for c in room.active_characters.all()],
        "fire": fire_dict(room, now),
        "welcome": welcome_text(room, hc),
        # 持ち主が承認した文だけが、外に出る
        "public_note": room.public_note,
        "is_mine": bool(viewer and room.owner_id == viewer.pk),
    }


def list_fires(viewer=None, limit=30, offset=0, now=None):
    now = now or timezone.now()
    cutoff = now - presence_ttl()
    qs = (
        Room.objects.exclude(kind=Room.KIND_LEGACY)
        .annotate(hc=Count("presences__user", distinct=True, filter=Q(presences__last_seen__gte=cutoff)))
        .annotate(
            rank=Case(
                When(hc__gte=F("capacity"), then=3),  # いっぱいの輪は後ろへ
                When(hc=1, then=0),                    # ひとりで火にあたっている人のところを最初に
                When(hc__gte=2, then=1),
                default=2,
                output_field=IntegerField(),
            )
        )
        .prefetch_related("active_characters")
        .order_by("rank", "-last_active_at", "-id")
    )
    total = qs.count()
    rows = list(qs[offset : offset + limit])
    return [fire_to_dict(r, r.hc, viewer, now) for r in rows], total


# ====================================
# AIキャラの出入り
# ====================================

def release_characters(room_id):
    """焚火からAIキャラを全員帰す。帰したキャラのリストを返す。"""
    room = Room.objects.filter(pk=room_id).first()
    if room is None:
        return []
    released = list(room.active_characters.all())
    if released:
        room.active_characters.clear()
    Room.objects.filter(pk=room_id).update(ai_join_after=None)
    return released


def acquire_character(room_id):
    """
    焚火に入れるキャラを1人探して入れる。返り値は (キャラ, 借りてきた元の焚火のid or None)。
    空いているキャラがいなければ、誰もいない「AIたちの焚火」から1人来てもらう。どちらも無ければ (None, None)。
    """
    room = Room.objects.filter(pk=room_id).first()
    if room is None:
        return None, None

    candidates = ai_manager.pick_characters_for_room(room, count=1)
    if candidates:
        room.active_characters.add(candidates[0])
        return candidates[0], None

    for donor in Room.objects.filter(kind=Room.KIND_AMBIENT).exclude(pk=room_id).distinct():
        if human_count(donor.pk) == 0:
            character = donor.active_characters.first()
            if character is not None:
                donor.active_characters.remove(character)
                room.active_characters.add(character)
                return character, donor.pk
    return None, None
