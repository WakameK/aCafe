import json
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .consumers import ROOMS
from .models import SpaceRoom


def _room_dict(room: SpaceRoom) -> dict:
    return {
        "slug": room.slug,
        "name": room.name,
        "count": len(ROOMS.get(room.slug, {})),
    }


# ※ 開発中はCSRFチェックを外している。ログイン機能と繋げるときに戻す
@csrf_exempt
@require_http_methods(["GET", "POST"])
def rooms(request):
    if request.method == "GET":
        return JsonResponse({"rooms": [_room_dict(r) for r in SpaceRoom.objects.all()]})

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "JSONの形式が正しくありません"}, status=400)

    name = str(body.get("name", "")).strip()
    if not name or len(name) > 30:
        return JsonResponse({"error": "部屋名は1〜30文字で入力してください"}, status=400)

    room = SpaceRoom.objects.create(slug=uuid.uuid4().hex[:8], name=name)
    return JsonResponse(_room_dict(room), status=201)


@require_http_methods(["GET"])
def room_detail(request, slug):
    room = SpaceRoom.objects.filter(slug=slug).first()
    if room is None:
        return JsonResponse({"error": "部屋が見つかりません"}, status=404)
    return JsonResponse(_room_dict(room))