from django.shortcuts import render
from django.http import JsonResponse
import json

def index(request):
    return render(request, "index.html")



def chat_page(request):
    return render(request, "chat.html")

def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        msg = data.get("message", "")
        return JsonResponse({"reply": f"『{msg}』って言ったね！"})

    return JsonResponse({"error": "POST only"}, status=400)