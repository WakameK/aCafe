"""
焚火(desk)のHTTP API。ベースは /api/desk/ 。

  GET    fires/                    焚火の一覧(?anon_id=&limit=&offset=)
  POST   fires/                    焚火を起こす
  PATCH  fires/<id>/               持ち主が焚火を変える(名前・テーマ・輪の人数・外向けのひとこと)
  DELETE fires/<id>/               持ち主が火を消す(焚火も発言も消える)
  POST   fires/<id>/join/          輪に入る準備(WebSocketの接続先と、いままでの発言を返す。display_name で名前も更新)
  GET    fires/<id>/messages/      発言の続き(輪にいる人だけ。?before= / ?after=)
  POST   fires/<id>/gifts/         薪・コーヒーなどを置く

本人確認は anon_id(ブラウザが持つ匿名ID)だけ。他の人の anon_id を知られないよう、API はどこにも anon_id を返さない。
"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import services
from .models import Room
from .services import FireError, cfg


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


def _json_body(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _guest(anon_id):
    if not services.valid_anon_id(anon_id):
        return None
    return services.get_or_create_guest(anon_id)


def _get_fire(fire_id):
    return Room.objects.exclude(kind=Room.KIND_LEGACY).filter(pk=fire_id).first()


def _int_param(request, name, default, low, high):
    try:
        value = int(request.GET.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def fires(request):
    if request.method == "GET":
        anon_id = request.GET.get("anon_id")
        viewer = services.get_or_create_guest(anon_id) if services.valid_anon_id(anon_id) else None
        limit = _int_param(request, "limit", 30, 1, 100)
        offset = _int_param(request, "offset", 0, 0, 100000)
        items, total = services.list_fires(viewer, limit=limit, offset=offset)
        return JsonResponse({"fires": items, "total": total})

    body = _json_body(request)
    if body is None:
        return _error("invalid json", 400)
    owner = _guest(body.get("anon_id"))
    if owner is None:
        return _error("anon_id is required", 400)
    try:
        room = services.create_fire(
            owner,
            name=body.get("name"),
            topic=body.get("topic", ""),
            capacity=body.get("capacity", 6),
        )
    except FireError as e:
        return _error(e.message, 400)
    return JsonResponse(services.fire_to_dict(room, 0, owner), status=201)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
def fire_detail(request, fire_id):
    body = _json_body(request)
    if body is None:
        return _error("invalid json", 400)
    user = _guest(body.get("anon_id"))
    if user is None:
        return _error("anon_id is required", 400)
    room = _get_fire(fire_id)
    if room is None:
        return _error("fire not found", 404)
    if room.owner_id != user.pk:
        return _error("この焚火を変えられるのは、起こした人だけです。", 403)

    if request.method == "DELETE":
        services.broadcast(room.id, {"type": "fire.out"})
        services.extinguish(room.id)
        return JsonResponse({"ok": True})

    try:
        room = services.update_fire(
            room,
            name=body.get("name"),
            topic=body.get("topic"),
            capacity=body.get("capacity"),
            public_note=body.get("public_note"),
        )
    except FireError as e:
        return _error(e.message, 400)
    services.broadcast(
        room.id,
        {
            "type": "fire.updated",
            "name": room.name,
            "topic": room.topic,
            "capacity": room.capacity,
            "public_note": room.public_note,
        },
    )
    return JsonResponse(services.fire_to_dict(room, services.human_count(room.id), user))


@csrf_exempt
@require_http_methods(["POST"])
def join(request, fire_id):
    body = _json_body(request)
    if body is None:
        return _error("invalid json", 400)
    anon_id = body.get("anon_id")
    user = _guest(anon_id)
    if user is None:
        return _error("anon_id is required", 400)
    room = _get_fire(fire_id)
    if room is None:
        return _error("fire not found", 404)
    services.set_display_name(user, body.get("display_name"))  # プロフィールで決めた名前

    count = services.human_count(room.id)
    already_here = services.active_presences(room.id).filter(user_id=user.pk).exists()
    if count >= room.capacity and not already_here:
        return _error("輪がいっぱいです。", 409)

    return JsonResponse(
        {
            "fire": services.fire_to_dict(room, count, user),
            "user": {"id": user.pk, "name": user.name},
            "ws_path": f"/ws/fires/{room.id}/?anon_id={anon_id}",
            "history": services.recent_messages(room.id, limit=cfg("DESK_JOIN_HISTORY_LIMIT", 30)),
            "gift_items": services.gift_items(),
            "note_draft": room.note_draft if room.owner_id == user.pk else "",
        },
        status=201,
    )


@require_http_methods(["GET"])
def messages(request, fire_id):
    user = _guest(request.GET.get("anon_id"))
    if user is None:
        return _error("anon_id is required", 400)
    room = _get_fire(fire_id)
    if room is None:
        return _error("fire not found", 404)
    # 輪の外から、発言を覗けないようにする
    if not services.active_presences(room.id).filter(user_id=user.pk).exists():
        return _error("輪に入っている人だけが読めます。", 403)

    limit = _int_param(request, "limit", 50, 1, 100)
    before = request.GET.get("before")
    after = request.GET.get("after")
    try:
        before = int(before) if before else None
        after = int(after) if after else None
    except ValueError:
        return _error("invalid cursor", 400)
    return JsonResponse(
        {"messages": services.recent_messages(room.id, limit=limit, before=before, after=after)}
    )


@csrf_exempt
@require_http_methods(["POST"])
def gifts(request, fire_id):
    body = _json_body(request)
    if body is None:
        return _error("invalid json", 400)
    user = _guest(body.get("anon_id"))
    if user is None:
        return _error("anon_id is required", 400)
    room = _get_fire(fire_id)
    if room is None:
        return _error("fire not found", 404)
    if not services.active_presences(room.id).filter(user_id=user.pk).exists():
        return _error("輪に入っている人だけが置けます。", 403)

    item = body.get("item") or "薪"
    if item not in services.gift_items():
        return _error("そのものは置けません。", 400)
    if services.recently_gave(room.id, user):
        return _error("少し待ってから、もう一度置いてください。", 429)

    gift, fire = services.give_gift(room.id, user, item, (body.get("message") or "").strip()[:100])
    services.broadcast(room.id, {"type": "chat.gift", "gift": gift})
    if fire is not None:
        services.broadcast(room.id, {"type": "fire.level", "fire": fire})
    return JsonResponse({"gift": gift, "fire": fire}, status=201)
