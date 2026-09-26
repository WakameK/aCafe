import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from sosuke.models import Users
from . import ai_manager
from .models import DrinkGift, Message, Room


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
