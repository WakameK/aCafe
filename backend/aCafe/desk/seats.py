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
from .models import Message, Room, Seat

logger = logging.getLogger(__name__)

STATUS_VACANT = "vacant"
STATUS_OCCUPIED = "occupied"
STATUS_FULL = "full"

# 座ってからWebSocketが繋がるまでの猶予。この間は人がいなくても「空席」にしない
SIT_GRACE = timedelta(seconds=getattr(settings, "DESK_SIT_GRACE_SECONDS", 30))
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


def _is_reserved(seat, now=None):
    now = now or timezone.now()
    return bool(seat.sat_at and now - seat.sat_at < SIT_GRACE)


def seat_status(seat, now=None):
    room = seat.room
    if room is None:
        return STATUS_VACANT
    if room.human_count >= seat.capacity:
        return STATUS_FULL
    if room.human_count > 0 or _is_reserved(seat, now):
        return STATUS_OCCUPIED
    return STATUS_VACANT


def sit(seat_id):
    """席に座る。そのRoomを返す。満席なら SeatFullError。"""
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
        return seat.room


def _release_characters(room):
    room.active_characters.clear()
    Room.objects.filter(pk=room.pk).update(ai_join_scheduled=False)


def release_room_if_empty(room_id):
    """席を離れた結果、人間が0人になった席のAIキャラを解放する(他の席/部屋に出られるようにする)。"""
    room = Room.objects.filter(pk=room_id).first()
    if room is None or room.human_count > 0 or not hasattr(room, "seat"):
        return
    _release_characters(room)


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
        "human_count": room.human_count if room and status != STATUS_VACANT else 0,
        "characters": [],
        "atmosphere": "",
    }
    if room is not None and status != STATUS_VACANT:
        data["characters"] = [c.name for c in room.active_characters.all()]
        if with_atmosphere:
            data["atmosphere"] = refresh_atmosphere(room)
    return data
