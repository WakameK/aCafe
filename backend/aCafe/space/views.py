import json
import uuid

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import fire
from .consumers import ROOMS
from .models import SpaceRoom


def _room_dict(room: SpaceRoom, occupants: int, now) -> dict:
    return {
        "slug": room.slug,
        "name": room.name,
        "count": occupants,
        "heat": round(fire.effective_heat(room, occupants, now), 3),
        "permanent": room.is_permanent,
    }


def _alive_rooms(now) -> list[dict]:
    """火の消えた部屋を片付けて、残っている部屋だけ返す"""
    result = []
    for room in list(SpaceRoom.objects.all()):
        occupants = len(ROOMS.get(room.slug, {}))
        if fire.is_extinguished(room, occupants, now):
            room.delete()
            continue
        result.append(_room_dict(room, occupants, now))
    return result


# ※ 開発中はCSRFチェックを外している。ログイン機能と繋げるときに戻す
@csrf_exempt
@require_http_methods(["GET", "POST"])
def rooms(request):
    now = timezone.now()

    if request.method == "GET":
        return JsonResponse({"rooms": _alive_rooms(now)})

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "JSONの形式が正しくありません"}, status=400)

    name = str(body.get("name", "")).strip()
    if not name or len(name) > 30:
        return JsonResponse({"error": "部屋名は1〜30文字で入力してください"}, status=400)

    room = SpaceRoom.objects.create(
        slug=uuid.uuid4().hex[:8],
        name=name,
        heat=fire.START_HEAT,
        heat_updated_at=now,
    )
    return JsonResponse(_room_dict(room, 0, now), status=201)


@require_http_methods(["GET"])
def room_detail(request, slug):
    now = timezone.now()
    room = SpaceRoom.objects.filter(slug=slug).first()
    if room is None:
        return JsonResponse({"error": "部屋が見つかりません"}, status=404)

    occupants = len(ROOMS.get(room.slug, {}))
    if fire.is_extinguished(room, occupants, now):
        room.delete()
        return JsonResponse({"error": "この部屋の焚火は消えました"}, status=404)

    return JsonResponse(_room_dict(room, occupants, now))