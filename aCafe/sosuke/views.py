from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import requests

def index(request):
    return render(request, "index.html")



def chat_page(request):
    return render(request, "chat.html")

@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        msg = data.get("message", "")

        payload = {
            "model": "alpaca",
            "prompt": msg
        }

        res = requests.post("http://localhost:11434/api/generate", json=payload)
        reply = res.json().get("response", "")

        return JsonResponse({"reply": reply})

    return JsonResponse({"error": "POST only"}, status=400)



