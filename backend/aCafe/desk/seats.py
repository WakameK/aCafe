"""
座席まわりのロジック(HTTP view と WebSocket consumer の両方から使う)。

- sit: 席に座る(空席なら新しいチャット空間=Roomを作る / 先客がいれば相席する)
- seat_status: 席の状態(vacant / occupied / full)
- seat_to_dict: 座席一覧用の表示データ。オーナーAIの「雰囲気ひとこと」も含む
- release_room_if_empty: 最後の1人が席を離れたときの後片付け(AIキャラを解放する)
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from sosuke.models import Users
from . import ai_manager
from .models import Message, Presence, Room, Seat

logger = logging.getLogger(__name__)

STATUS_VACANT = "vacant"
STATUS_OCCUPIED = "occupied"
STATUS_FULL = "full"

# 座ってからWebSocketが繋がるまでの猶予。この間は人がいなくても「空席」にしない
SIT_GRACE = timedelta(seconds=getattr(settings, "DESK_SIT_GRACE_SECONDS", 30))
# 在席の有効期間。クライアントが定期的にpingして更新する。これを過ぎた接続は在席に数えない
PRESENCE_TTL = timedelta(seconds=getattr(settings, "DESK_PRESENCE_TTL_SECONDS", 120))
# 空席がこの数を下回ったら、座席を追加する(上限まで)
MIN_VACANT_SEATS = getattr(settings, "DESK_MIN_VACANT_SEATS", 2)
MAX_SEATS = getattr(settings, "DESK_MAX_SEATS", 30)
EXTRA_SEAT_CAPACITY = 4
# 雰囲気ひとことを作り直す最短間隔(Ollamaを叩きすぎない)
ATMOSPHERE_MIN_INTERVAL = timedelta(seconds=getattr(settings, "DESK_ATMOSPHERE_MIN_SECONDS", 60))
ATMOSPHERE_TIMEOUT = getattr(settings, "DESK_ATMOSPHERE_TIMEOUT", 8)

QUIET_ATMOSPHERE = "座ったばかりで、まだ静かな席です。"


class SeatFullError(Exception):
    pass


def get_or_create_guest(anon_id):
    """WebSocketのconsumerと同じ規則で匿名ユーザーを取得/作成する。"""
    anon_id = anon_id or "anonymous"
    user, _ = Users.objects.get_or_create(
        anon_id=anon_id, defaults={"name": f"ゲスト-{anon_id[:6]}"}
    )
    return user


def live_count(room, now=None):
    now = now or timezone.now()
    return Presence.objects.filter(room=room, last_seen__gte=now - PRESENCE_TTL).count()


def enter(room_id, channel_name):
    """入室して在席に加わる。座席の定員を超えるなら False。"""
    with transaction.atomic():
        room = Room.objects.select_for_update().get(pk=room_id)
        seat = getattr(room, "seat", None)
        if seat is not None and live_count(room) >= seat.capacity:
            return False
        Presence.objects.update_or_create(
            channel_name=channel_name, defaults={"room": room, "last_seen": timezone.now()}
        )
        return True


def touch(room_id, channel_name):
    """在席の更新(クライアントのpingで呼ぶ)。期限切れで消えていても作り直す。"""
    Presence.objects.update_or_create(
        channel_name=channel_name,
        defaults={"room_id": room_id, "last_seen": timezone.now()},
    )


def leave(room_id, channel_name):
    Presence.objects.filter(channel_name=channel_name).delete()
    release_room_if_empty(room_id)


def purge_stale_presences():
    """期限切れの在席を消し、無人になった部屋のキャラを解放する。"""
    cutoff = timezone.now() - PRESENCE_TTL
    stale = Presence.objects.filter(last_seen__lt=cutoff)
    room_ids = set(stale.values_list("room_id", flat=True))
    if not room_ids:
        return
    stale.delete()
    for room_id in room_ids:
        release_room_if_empty(room_id)


def ensure_vacant_seats():
    """空席が足りなければ座席を増やす(席が埋まったら都度追加される)。"""
    seats = list(Seat.objects.select_related("room"))
    vacant = sum(1 for s in seats if seat_status(s) == STATUS_VACANT)
    total = len(seats)
    labels = {s.label for s in seats}
    number = total
    while vacant < MIN_VACANT_SEATS and total < MAX_SEATS:
        number += 1
        label = f"テーブル席{number}"
        if label in labels:
            continue
        Seat.objects.create(label=label, capacity=EXTRA_SEAT_CAPACITY)
        labels.add(label)
        total += 1
        vacant += 1


def _is_reserved(seat, now=None):
    now = now or timezone.now()
    return bool(seat.sat_at and now - seat.sat_at < SIT_GRACE)


def seat_status(seat, now=None):
    room = seat.room
    if room is None:
        return STATUS_VACANT
    count = live_count(room)
    if count >= seat.capacity:
        return STATUS_FULL
    if count > 0 or _is_reserved(seat, now):
        return STATUS_OCCUPIED
    return STATUS_VACANT


def sit(seat_id):
    """席に座る。そのRoomを返す。満席なら SeatFullError。"""
    purge_stale_presences()
    with transaction.atomic():
        seat = Seat.objects.select_for_update().select_related("room").get(pk=seat_id)
        status = seat_status(seat)
        if status == STATUS_FULL:
            raise SeatFullError(seat.label)

        if status == STATUS_VACANT:
            # 前のチャット空間は閉じて、新しい空間を作る
            if seat.room is not None:
                _release_characters(seat.room)
            seat.room = Room.objects.create(name=seat.label)
        seat.sat_at = timezone.now()
        seat.save(update_fields=["room", "sat_at"])
        room = seat.room
    ensure_vacant_seats()
    return room


def _release_characters(room):
    room.active_characters.clear()
    Room.objects.filter(pk=room.pk).update(ai_join_scheduled=False)


def release_room_if_empty(room_id):
    """席を離れた結果、人間が0人になった席のAIキャラを解放する(他の席/部屋に出られるようにする)。"""
    room = Room.objects.filter(pk=room_id).first()
    if room is None or live_count(room) > 0:
        return
    _release_characters(room)
    seat = getattr(room, "seat", None)
    if seat is not None:
        # 座った直後の予約も解除する(離れたのに「誰かいます」のままにしない)
        Seat.objects.filter(pk=seat.pk).update(sat_at=None)


def refresh_atmosphere(room, now=None):
    """
    必要なら雰囲気ひとことを作り直して、いまの文を返す。
    - 前回の生成後に新しい発言がなければ作り直さない
    - 失敗(Ollama停止など)しても例外は出さず、古い文を返す
    """
    now = now or timezone.now()
    last = Message.objects.filter(room=room).order_by("-created_at").first()
    if last is None:
        return QUIET_ATMOSPHERE

    updated = room.atmosphere_updated_at
    if updated and (last.created_at <= updated or now - updated < ATMOSPHERE_MIN_INTERVAL):
        return room.atmosphere_summary

    recent = list(Message.objects.filter(room=room).order_by("-created_at")[:20])
    recent_text = ai_manager.format_recent_messages(reversed(recent))
    try:
        summary = ai_manager.generate_room_atmosphere_summary(
            room, recent_text, timeout=ATMOSPHERE_TIMEOUT
        ).strip()
    except Exception:
        logger.warning("atmosphere generation failed for room %s", room.pk, exc_info=True)
        summary = room.atmosphere_summary

    # 失敗時も更新時刻は進めて、Ollamaが落ちている間に毎回待たされないようにする
    room.atmosphere_summary = summary
    room.atmosphere_updated_at = now
    room.save(update_fields=["atmosphere_summary", "atmosphere_updated_at"])
    return summary


def seat_to_dict(seat, with_atmosphere=True):
    status = seat_status(seat)
    room = seat.room
    data = {
        "id": seat.id,
        "label": seat.label,
        "capacity": seat.capacity,
        "status": status,
        "human_count": live_count(room) if room and status != STATUS_VACANT else 0,
        "characters": [],
        "atmosphere": "",
    }
    if room is not None and status != STATUS_VACANT:
        data["characters"] = [c.name for c in room.active_characters.all()]
        if with_atmosphere:
            data["atmosphere"] = refresh_atmosphere(room)
    return data
