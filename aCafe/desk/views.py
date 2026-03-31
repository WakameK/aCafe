from django.shortcuts import render
from django.http import JsonResponse
from .models import Room, Message

def room_view(request):
    room = Room.objects.first()  # 最初の部屋を使う
    return render(request, "room.html", {"room": room})

def send_message(request):
    user = request.anon_user
    content = request.POST.get("content")

    room = Room.objects.first()

    Message.objects.create(
        room=room,
        user=user,
        content=content
    )

    return JsonResponse({"status": "ok"})

def get_messages(request):
    room = Room.objects.first()
    messages = Message.objects.filter(room=room)

    data = [
        {
            "user": msg.user.name,
            "content": msg.content,
            "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M")
        }
        for msg in messages
    ]

    return JsonResponse({"messages": data})


def create_room(request):
    if request.method == "POST":
        name = request.POST.get("name")
        room = Room.objects.create(name=name)
        return JsonResponse({"status": "ok", "room_id": room.id})

