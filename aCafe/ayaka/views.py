from django.shortcuts import render
from sosuke.models import ChatLog
from sosuke.views import call_llm_api  # 既存の関数をインポート
from django.http import JsonResponse
from config.settings_loader import get_config
import requests

# =======================================================================
# atelier: 彩花のアトリエページ
# =======================================================================
def atelier(request):
    return render(request, "atelier.html")

# =======================================================================
# get_recent_messages: ユーザーの最近のメッセージを取得する関数
# ======================================================================
def get_recent_messages(user, limit=20):
    logs = ChatLog.objects.filter(user=user).order_by('-created_at')[:limit]
    messages = [log.message for log in logs if log.role == "user"]
    return "\n".join(messages)

# ====================================================================================================
# build_prompt_from_messages: ユーザーの会話内容から画像生成用のプロンプトを作成する関数
# ====================================================================================================
def build_prompt_from_messages(messages: str):
    system_prompt = get_config('ayaka.image_generation.system_prompt')
    user_format = get_config('ayaka.image_generation.user_format')
    return system_prompt + "\n\n" + user_format.format(messages=messages)

# ======================================================================
# generate_image: プロンプトを元に画像を生成する関数
# ======================================================================
def generate_image(prompt: str):
    url = "https://api.pixazo.com/v1/image"
    payload = {
        "model": "sdxl",
        "prompt": prompt,
        "width": 1024,
        "height": 1024
    }
    res = requests.post(url, json=payload)
    data = res.json()
    return data.get("url")  # 生成された画像URL

# ======================================================================================
# generate_cafe_image: ユーザーの会話内容からそれっぽい絵を生成するビュー関数
# ======================================================================================
def generate_cafe_image(request):
    user = request.user  # もしくは anon_user_id から取得

    # 1. ChatLog からメッセージ取得
    messages = get_recent_messages(user)

    # 2. プロンプト生成（Ollama）
    prompt_for_llm = build_prompt_from_messages(messages)
    llm_prompt = call_llm_api({"prompt": prompt_for_llm})  # ← gemma3 で実装済みの関数を使う

    # 3. 画像生成APIに投げる
    image_url = generate_image(llm_prompt)

    return JsonResponse({"image_url": image_url})
