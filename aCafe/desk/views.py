from django.shortcuts import render
from django.http import JsonResponse
from .models import Room, Message

# ---------------------------------------------------------
# room_view
# ---------------------------------------------------------
# チャットルーム画面を表示するビュー。
# 現状は「最初の Room を1つだけ使う」仕様のため、
# Room.objects.first() を取得してテンプレートに渡す。
# ---------------------------------------------------------
def chat_view(request, room_id):
    room = Room.objects.get(id=room_id)
    return render(request, "desk/chat.html", {"room": room})

def room_view(request):
    rooms = Room.objects.all().order_by("-created_at")
    return render(request, "desk/room.html", {"rooms": rooms})



# ---------------------------------------------------------
# send_message
# ---------------------------------------------------------
# POSTされたメッセージを現在のルームに保存する。
# 匿名ユーザー(request.anon_user)を利用しているため、
# ログイン不要でメッセージ投稿が可能。
# 成功時は {"status": "ok"} を返す。
# ---------------------------------------------------------
def send_message(request):
    user = request.anon_user
    content = request.POST.get("content")
    room_id = request.POST.get("room_id")

    try:
        room = Room.objects.get(id=room_id)
    except Room.DoesNotExist:
        return JsonResponse({"status": "error", "message": "ルームが見つかりません"})

    Message.objects.create(
        room=room,
        user=user,
        content=content
    )

    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------
# get_messages
# ---------------------------------------------------------
# 現在のルームに紐づくメッセージ一覧を取得し、
# JSON形式で返すAPI。
# created_at は "YYYY-MM-DD HH:MM" 形式に整形。
# ---------------------------------------------------------
def get_messages(request):
    room_id = request.GET.get("room_id")
    if not room_id:
        return JsonResponse({"messages": []})
    
    try:
        room = Room.objects.get(id=room_id)
    except Room.DoesNotExist:
        return JsonResponse({"messages": []})
    
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


# ---------------------------------------------------------
# create_room
# ---------------------------------------------------------
# 新しいチャットルームを作成するAPI。
# POSTで送られた name を使って Room を作成し、
# 生成された room_id を JSON で返す。
# ---------------------------------------------------------
def create_room(request):
    if request.method == "POST":
        name = request.POST.get("name")
        room = Room.objects.create(name=name)
        return JsonResponse({"status": "ok", "room_id": room.id})
