"""
テーブルまわりのロジック(HTTP view と WebSocket consumer の両方から使う)。

店内は「テーブルを繋げた1つの大きな空間」。テーブルは話題ごとに作られ、人数の上限は無い。

- create_table: 話題を付けてテーブルを作る
- sit: 既にあるテーブルに座る(誰かいれば同じチャット空間に合流する)
- table_status: テーブルの状態(vacant / occupied)
- table_to_dict: テーブル一覧用の表示データ。オーナーAIの「雰囲気ひとこと」も含む
- close_empty_tables: 誰もいなくなった(常設でない)テーブルを片付ける
- release_room_if_empty: 最後の1人が離れたときの後片付け(AIキャラを解放する)
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from sosuke.models import Users
from . import ai_manager
from .models import Message, Presence, Room, Table

logger = logging.getLogger(__name__)

STATUS_VACANT = "vacant"
STATUS_OCCUPIED = "occupied"

# 座ってからWebSocketが繋がるまでの猶予。この間は人がいなくても「空き」にしない
SIT_GRACE = timedelta(seconds=getattr(settings, "DESK_SIT_GRACE_SECONDS", 30))
# 在席の有効期間。クライアントが定期的にpingして更新する。これを過ぎた接続は在席に数えない
PRESENCE_TTL = timedelta(seconds=getattr(settings, "DESK_PRESENCE_TTL_SECONDS", 120))
# テーブル数の上限(作りっぱなしの荒らし対策)と、話題名の最大文字数
MAX_TABLES = getattr(settings, "DESK_MAX_TABLES", 50)
TABLE_NAME_MAX = 30
# 雰囲気ひとことを作り直す最短間隔(Ollamaを叩きすぎない)
ATMOSPHERE_MIN_INTERVAL = timedelta(seconds=getattr(settings, "DESK_ATMOSPHERE_MIN_SECONDS", 60))
ATMOSPHERE_TIMEOUT = getattr(settings, "DESK_ATMOSPHERE_TIMEOUT", 8)

QUIET_ATMOSPHERE = "座ったばかりで、まだ静かなテーブルです。"


class InvalidTableName(Exception):
    pass


class TableLimitError(Exception):
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
    """入室して在席に加わる。"""
    Presence.objects.update_or_create(
        channel_name=channel_name,
        defaults={"room_id": room_id, "last_seen": timezone.now()},
    )


def touch(room_id, channel_name):
    """在席の更新(クライアントのpingで呼ぶ)。期限切れで消えていても作り直す。"""
    enter(room_id, channel_name)


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


def _is_reserved(table, now=None):
    now = now or timezone.now()
    return bool(table.sat_at and now - table.sat_at < SIT_GRACE)


def table_status(table, now=None):
    room = table.room
    if room is None:
        return STATUS_VACANT
    if live_count(room, now) > 0 or _is_reserved(table, now):
        return STATUS_OCCUPIED
    return STATUS_VACANT


def create_table(name):
    """話題を付けてテーブルを作る。チャット空間(Room)も同時に作る。"""
    name = (name or "").strip()
    if not name or len(name) > TABLE_NAME_MAX:
        raise InvalidTableName(name)
    with transaction.atomic():
        if Table.objects.count() >= MAX_TABLES:
            raise TableLimitError()
        room = Room.objects.create(name=name)
        return Table.objects.create(name=name, room=room, sat_at=timezone.now())


def sit(table_id):
    """テーブルに座る。そのRoomを返す。人がいなければ新しいチャット空間にする。"""
    purge_stale_presences()
    with transaction.atomic():
        table = Table.objects.select_for_update().select_related("room").get(pk=table_id)
        if table_status(table) == STATUS_VACANT:
            # 前のチャット空間は閉じて、新しい空間を作る
            if table.room is not None:
                _release_characters(table.room)
            table.room = Room.objects.create(name=table.name)
        table.sat_at = timezone.now()
        table.save(update_fields=["room", "sat_at"])
        return table.room


def _release_characters(room):
    room.active_characters.clear()
    Room.objects.filter(pk=room.pk).update(ai_join_scheduled=False)


def release_room_if_empty(room_id):
    """テーブルを離れた結果、人間が0人になった部屋のAIキャラを解放する(他の部屋に出られるようにする)。"""
    room = Room.objects.filter(pk=room_id).first()
    if room is None or live_count(room) > 0:
        return
    _release_characters(room)
    table = getattr(room, "table", None)
    if table is not None:
        # 座った直後の予約も解除する(離れたのに「誰かいます」のままにしない)
        Table.objects.filter(pk=table.pk).update(sat_at=None)


def close_empty_tables():
    """誰もいなくなった、常設でないテーブルを片付ける(部屋と発言ログはDBに残す)。"""
    for table in Table.objects.filter(is_permanent=False).select_related("room"):
        if table_status(table) == STATUS_VACANT:
            if table.room is not None:
                _release_characters(table.room)
            table.delete()


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


def table_to_dict(table, with_atmosphere=True):
    status = table_status(table)
    room = table.room
    data = {
        "id": table.id,
        "name": table.name,
        "is_permanent": table.is_permanent,
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
