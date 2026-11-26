import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from sosuke.models import Users
from . import ai_manager
from .models import DrinkGift, Message, Room, Table
from .tables import (
    TABLE_NAME_MAX,
    InvalidTableName,
    TableLimitError,
    close_empty_tables,
    create_table,
    get_or_create_guest,
    purge_stale_presences,
    sit,
    table_to_dict,
)


def _room_to_dict(room):
    return {
        "id": room.id,
        "name": room.name,
        "topic": room.topic,
        "mode": room.mode,
        "atmosphere_summary": room.atmosphere_summary,
        "active_characters": [c.name for c in room.active_characters.all()],
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
def rooms(request):
    if request.method == "GET":
        data = [_room_to_dict(r) for r in Room.objects.all().prefetch_related("active_characters")]
        return JsonResponse({"rooms": data})

    body = json.loads(request.body or "{}")
    room = Room.objects.create(
        name=body.get("name", "無題の部屋"),
        topic=body.get("topic", ""),
        mode=body.get("mode", Room.MODE_TALK),
    )
    return JsonResponse(_room_to_dict(room), status=201)


@csrf_exempt
@require_http_methods(["POST"])
def regenerate_atmosphere(request, room_id):
    try:
        room = Room.objects.get(pk=room_id)
    except Room.DoesNotExist:
        return JsonResponse({"error": "room not found"}, status=404)

    recent = Message.objects.filter(room_id=room_id).order_by("-created_at")[:20]
    recent_text = ai_manager.format_recent_messages(reversed(list(recent)))
    summary = ai_manager.generate_room_atmosphere_summary(room, recent_text)

    room.atmosphere_summary = summary
    from django.utils import timezone
    room.atmosphere_updated_at = timezone.now()
    room.save(update_fields=["atmosphere_summary", "atmosphere_updated_at"])

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"room_{room_id}",
        {"type": "chat.atmosphere", "summary": summary},
    )
    return JsonResponse({"summary": summary})


@csrf_exempt
@require_http_methods(["POST"])
def send_gift(request, room_id):
    body = json.loads(request.body or "{}")
    try:
        from_user = Users.objects.get(pk=body["from_user_id"])
    except (KeyError, Users.DoesNotExist):
        return JsonResponse({"error": "from_user_id is required and must exist"}, status=400)

    to_user = None
    if body.get("to_user_id"):
        try:
            to_user = Users.objects.get(pk=body["to_user_id"])
        except Users.DoesNotExist:
            return JsonResponse({"error": "to_user_id does not exist"}, status=400)

    gift = DrinkGift.objects.create(
        room_id=room_id,
        from_user=from_user,
        to_user=to_user,
        item_name=body.get("item_name", "コーヒー"),
        message=body.get("message", ""),
    )

    gift_data = {
        "id": gift.id,
        "from_user": from_user.name,
        "to_user": to_user.name if to_user else None,
        "item_name": gift.item_name,
        "message": gift.message,
    }

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"room_{room_id}",
        {"type": "chat.gift", "gift": gift_data},
    )
    return JsonResponse(gift_data, status=201)


# ====================================
# テーブル
# ====================================

def _session_payload(table, room, user, anon_id):
    return {
        "table": table_to_dict(table, with_atmosphere=False),
        "room_id": room.id,
        "ws_path": f"/ws/rooms/{room.id}/?anon_id={anon_id}",
        "user": {"id": user.user_id, "name": user.name},
    }


def _read_anon_id(request):
    """リクエストのJSONからanon_idを取り出す。(body, anon_id, エラー応答) を返す。"""
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None, None, JsonResponse({"error": "invalid json"}, status=400)
    anon_id = body.get("anon_id")
    if not anon_id:
        return None, None, JsonResponse({"error": "anon_id is required"}, status=400)
    return body, anon_id, None


@csrf_exempt
@require_http_methods(["GET", "POST"])
def tables(request):
    """
    GET: テーブル一覧。誰かいるか・どんな雰囲気かを、座る前に確認できる。
    POST: 話題を付けてテーブルを作り、そのまま座る。
    """
    if request.method == "GET":
        purge_stale_presences()
        close_empty_tables()
        all_tables = Table.objects.select_related("room").prefetch_related("room__active_characters")
        data = [table_to_dict(t) for t in all_tables]
        return JsonResponse(
            {"tables": data, "floor": {"human_count": sum(t["human_count"] for t in data)}}
        )

    body, anon_id, error = _read_anon_id(request)
    if error:
        return error
    try:
        table = create_table(body.get("name"))
    except InvalidTableName:
        return JsonResponse({"error": f"name must be 1-{TABLE_NAME_MAX} characters"}, status=400)
    except TableLimitError:
        return JsonResponse({"error": "too many tables"}, status=409)

    user = get_or_create_guest(anon_id)
    return JsonResponse(_session_payload(table, table.room, user, anon_id), status=201)


@csrf_exempt
@require_http_methods(["POST"])
def sit_table(request, table_id):
    """テーブルに座る。誰かいれば、そのテーブルの会話に合流する。"""
    _, anon_id, error = _read_anon_id(request)
    if error:
        return error
    try:
        room = sit(table_id)
    except Table.DoesNotExist:
        return JsonResponse({"error": "table not found"}, status=404)

    user = get_or_create_guest(anon_id)
    table = Table.objects.select_related("room").get(pk=table_id)
    return JsonResponse(_session_payload(table, room, user, anon_id), status=201)
