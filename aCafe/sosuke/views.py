# ================================================================================
# urls.pyで定義したviewsを実装するためのファイル
# ===============================================================================
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Users, ChatLog
from config.settings_loader import get_config

import json
import requests
import uuid



# ========================================================================
# index: トップページ
# ========================================================================
def index(request):
    anon_id = request.COOKIES.get("anon_user_id")

    if anon_id:
        try:
            user = Users.objects.get(anon_id=anon_id)
            return render(request, "index.html", {"user": user})
        except Users.DoesNotExist:
            pass

    anon_id = str(uuid.uuid4())
    user = Users.objects.create(
        anon_id=anon_id,
        name="お客さん",
        login_key=None
    )

    response = render(request, "index.html", {"user": user})
    response.set_cookie("anon_user_id", anon_id, max_age=60*60*24*365)
    return response




    
# =======================================================================
# profile: ユーザープロフィールページ
# =======================================================================
def profile(request):
    return render(request, "profile.html")


# ========================================================================
# 初回ログイン登録のAPIエンドポイント
# =======================================================================
def register(request):
    if request.method == "POST":
        anon_id = request.COOKIES.get("anon_user_id")

        if not anon_id:
            return JsonResponse({"error": "cookie がありません"}, status=400)

        try:
            user = Users.objects.get(anon_id=anon_id)
        except Users.DoesNotExist:
            return JsonResponse({"error": "ユーザーが存在しません"}, status=400)

        user.name = request.POST.get("name")
        user.login_key = request.POST.get("login_key")
        user.save()

        return JsonResponse({"status": "ok"})


# ===========================================================================
# ログインページ / 会員登録ページ
# ===========================================================================
def login_page(request):
    return render(request,"login.html")



# ========================================================================
# 合言葉（login_key）を登録・更新する API
# ========================================================================
def update_login_key(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST で送ってください"}, status=400)

    anon_id = request.COOKIES.get("anon_user_id")
    if not anon_id:
        return JsonResponse({"error": "cookie がありません"}, status=400)

    try:
        user = Users.objects.get(anon_id=anon_id)
    except Users.DoesNotExist:
        return JsonResponse({"error": "ユーザーが存在しません"}, status=400)

    new_key = request.POST.get("login_key")
    if not new_key:
        return JsonResponse({"error": "合言葉が空です"}, status=400)

    user.login_key = new_key
    user.save()

    return JsonResponse({"status": "ok", "message": "合言葉を更新しました"})



# ========================================================================
# 再入場処理
# =======================================================================
def login(request):
    if request.method == "POST":
        name = request.POST.get("name")
        key = request.POST.get("login_key")

        try:
            user = Users.objects.get(name=name, login_key=key)
        except Users.DoesNotExist:
            return JsonResponse({"error": "名前または合言葉が違います"}, status=400)

        response = JsonResponse({"status": "ok"})
        response.set_cookie("anon_user_id", user.anon_id, max_age=60*60*24*365)
        return response
    return render(request, "login.html")

# ========================================================================
# 名前の更新処理
# =======================================================================
def update_name(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST で送ってください"}, status=400)

    anon_id = request.COOKIES.get("anon_user_id")
    if not anon_id:
        return JsonResponse({"error": "cookie がありません"}, status=400)

    try:
        user = Users.objects.get(anon_id=anon_id)
    except Users.DoesNotExist:
        return JsonResponse({"error": "ユーザーが存在しません"}, status=400)

    new_name = request.POST.get("name")
    if not new_name:
        return JsonResponse({"error": "名前が空です"}, status=400)

    user.name = new_name
    user.save()

    return JsonResponse({"status": "ok", "message": "名前を更新しました"})




# ========================================================================
# chat_page: 聡介とのチャットページ
# =======================================================================
def chat_page(request):
    return render(request, "chat.html")
# =======================================================================
# chat_api: 聡介の傾聴チャットのAPIエンドポイント
# =======================================================================
@csrf_exempt
def chat_api(request):

    # ★ ① Cookie が無ければ自動登録
    anon_id = request.COOKIES.get("anon_user_id")
    if not anon_id:
        anon_id = str(uuid.uuid4())
        user = Users.objects.create(
            anon_id=anon_id,
            name="名無し",
            login_key=None
        )
        response = JsonResponse({"status": "auto_registered"})
        response.set_cookie("anon_user_id", anon_id, max_age=60*60*24*365)
        return response

    # ★ ② Cookie がある → DB からユーザー取得
    try:
        user = Users.objects.get(anon_id=anon_id)
    except Users.DoesNotExist:
        return JsonResponse({"need_register": True})

    # ★ ③ ここから先はあなたの元コードそのまま
    if request.method == "POST":
        data = json.loads(request.body)
        msg = data.get("message", "")

        ChatLog.objects.create(
            user=user,
            role="user",
            message=msg
        )
        # プロンプトをconfig/prompt.jsonから取得
        model = get_config('sosuke.listening_chat.model')
        system_prompt = get_config('sosuke.listening_chat.system_prompt')
        user_format = get_config('sosuke.listening_chat.user_format')
        
        full_prompt = system_prompt + "\n\n" + user_format.format(message=msg)
        
        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
        }

        res = requests.post("http://localhost:11434/api/generate", json=payload)
        data = res.json()

        reply = (
            data.get("response") or
            data.get("output") or
            data.get("message") or
            data.get("content") or
            data.get("text") or
            ""
        )

        ChatLog.objects.create(
            user=user,
            role="sosuke",
            message=reply
        )

        return JsonResponse({"reply": reply})

    return JsonResponse({"error": "POST only"}, status=400)

# =======================================================================
# chat: チャットのやりとりを処理するビュー
# =======================================================================
def chat(request):
    user = request.user
    user_message = request.POST.get("message")

    # ① ユーザーの発言を保存
    ChatLog.objects.create(
        user=user,
        role="user",
        message=user_message
    )

    # ② LLM に問い合わせ
    ai_reply = call_llm_api(user_message)

    # ③ AI の返答を保存
    ChatLog.objects.create(
        user=user,
        role="assistant",
        message=ai_reply
    )

    return JsonResponse({"reply": ai_reply})

# =======================================================================
# 会話ログをJSON形式で取得する関数
# =======================================================================
def get_conversation_json(user, limit=30):
    logs = ChatLog.objects.filter(user=user).order_by("-created_at")[:limit]
    logs = reversed(logs)  # 時系列に戻す

    conversation = []
    for log in logs:
        conversation.append({
            "role": log.role,
            "content": log.message
        })

    return conversation





# ========================================================================
# デバッグ用のuuid確認関数
# ========================================================================
def debug_create_user(request):
    anon_id = str(uuid.uuid4())
    Users.objects.create(anon_id=anon_id, name="test", login_key="test")
    response = JsonResponse({"status": "ok"})
    response.set_cookie("anon_user_id", anon_id)
    return response

# =======================================================================
# export_chat_log: チャットログをJSON形式でダウンロード
# =======================================================================
def export_chat_log(request):
    anon_id = request.COOKIES.get("anon_user_id")
    
    if not anon_id:
        return JsonResponse({"error": "ユーザーが識別できません"}, status=400)
    
    try:
        user = Users.objects.get(anon_id=anon_id)
    except Users.DoesNotExist:
        return JsonResponse({"error": "ユーザーが見つかりません"}, status=404)
    
    # ユーザーのすべてのチャットログを取得
    logs = ChatLog.objects.filter(user=user).order_by("created_at")
    
    conversation = []
    for log in logs:
        conversation.append({
            "role": log.role,
            "message": log.message,
            "created_at": log.created_at.isoformat()
        })
    
    response = JsonResponse({
        "user_name": user.name,
        "user_id": user.user_id,
        "conversation": conversation
    }, json_dumps_params={"ensure_ascii": False})
    
    response["Content-Disposition"] = f'attachment; filename="chat_log_{user.anon_id[:8]}.json"'
    return response

# =========================================================
# 情報提供書作成のllm呼び出し
# =========================================================


def call_llm_api(prompt: dict):
    """
    Ollama のローカル LLM に相談シート生成を依頼する関数
    prompt は dict を想定
    """

    # prompt(dict) → JSON文字列に変換して LLM に渡す
    user_content = json.dumps(prompt, ensure_ascii=False)

    payload = {
        "model": "gemma3:4b",     #後で変える
        "prompt": user_content,
        "stream": False        # まとめて返す
    }

    response = requests.post(
        "http://localhost:11434/api/generate",
        json=payload
    )

    result = response.json()

    # Ollama は "response" キーに生成テキストが入る
    return {
        "response": result.get("response", "")
    }


# =======================================================================
# InformationSheet: 情報提供書の作成ロジック
# =========================================================================

def create_information_sheet(user):
    conversation = get_conversation_json(user)

    prompt = {
        "instruction": f"""
            以下の会話ログから相談シートとしてcsvファイルを作成してください。
            相談シートは、ユーザーの悩みや状況を整理するためのものです。
            以下の項目を含めて、ユーザーの情報をまとめてください。
                severity = models.IntegerField()                                    #ユーザーの困り度(1~5の整数で大きいほど困っている)
                worries = models.TextField()                         #ユーザーの悩み
                sleepStatus = models.TextField()                     #ユーザーの睡眠状況
                appetiteStatus = models.TextField()                  #ユーザーの食欲状況
                functioning = models.TextField()                     #ユーザーの日常機能
                physicalSymptoms = models.TextField()                #ユーザーの身体的症状
                mentalSymptoms = models.TextField()                  #ユーザーの精神的症状
                consultationGoal = models.TextField()                #薬の相談
                duration = models.TextField()                         #ユーザーの症状開始からの期間
                mainComplaint = models.TextField()                   #ユーザーの主訴
                changesFromBefore = models.TextField()               #ユーザーの症状発生以前からの変化
                cues = models.TextField()                            #症状が発生するきっかけ
                timeZone = models.TextField()                        #症状が発生する時間帯
                suicidalIdeation = models.TextField()                #ユーザーの自殺念慮
                questions = models.TextField()                       #ユーザーからの質問
                supportNeeded = models.TextField()                   #ユーザーが次の診察で必要としている支援

            会話ログ:
            {conversation}
        """,
        "conversation": conversation
    }


    response = call_llm_api(prompt)
    
    return response