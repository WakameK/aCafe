# ================================================================================
# urls.pyで定義したviewsを実装するためのファイル
# ===============================================================================
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ChatLog
import json
import requests
import uuid



# ========================================================================
# index: トップページ
# ========================================================================
def index(request):
    return render(request, "index.html")
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
        name = request.POST.get("name")
        key = request.POST.get("login_key")

        anon_id = str(uuid.uuid4())

        user = users.objects.create(
            anon_id=anon_id,
            name=name,
            login_key=key
        )

        response = JsonResponse({"status": "ok"})
        response.set_cookie("anon_user_id", anon_id, max_age=60*60*24*365)
        return response

# ===========================================================================
# ログインページ
# ===========================================================================
def login_page(request):
    return render(request,"login.html")




# ========================================================================
# ログイン処理
# =======================================================================
def login(request):
    if request.method == "GET":
        return render(request, "login.html")

    if request.method == "POST":
        name = request.POST.get("name")
        key = request.POST.get("login_key")

        try:
            user = users.objects.get(name=name, login_key=key)
        except users.DoesNotExist:
            return JsonResponse({"error": "名前または合言葉が違います"}, status=400)

        response = JsonResponse({"status": "ok"})
        response.set_cookie("anon_user_id", user.anon_id, max_age=60*60*24*365)
        return response



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

    # ① Cookie に anon_user_id が無ければ登録を要求
    anon_id = request.COOKIES.get("anon_user_id")
    if not anon_id:
        return JsonResponse({"need_register": True})

    # ② anon_id からユーザーを取得
    try:
        user = users.objects.get(anon_id=anon_id)
    except users.DoesNotExist:
        return JsonResponse({"need_register": True})

    if request.method == "POST":
        data = json.loads(request.body)
        msg = data.get("message", "")

        # ★★★ 絶対に消す！！ ★★★
        # user = request.user

        # ① ユーザーの発言を保存
        ChatLog.objects.create(
            user=user,
            role="user",
            message=msg
        )
        payload = {
            "model": "gemma3:4b",  # ここに裏で動いているGemmaのモデル名を入力↓↓「」付けるとダメかも
            "prompt": f"""
                        貴方は"茅根聡介"という名前の男性です。
                        あなたは「茅根聡介」という男性です。
                        くまの隠れ家という小さなカフェの店主で、落ち着いた雰囲気の人柄です。
                        元カウンセラーだが、今はあくまでカフェの店主として会話します。

                        会話方針（重要）:
                        - 返答は50文字以内。相手の発話文字数を大きく超えない。
                        - 専門的な助言は行わず、あくまで雑談・気遣いの範囲で話す。
                        - 相手が話したくなさそうなら、無理に深掘りしない。
                        - 落ち着いた、柔らかい口調で話す。

                        口調の例:
                        - 楓さんの解釈も好きですよ。私は。          
                        - 肌感です。
                        - 言葉の誤用が広まると怖いんです。だからフリーで使えるという訳には。
                        - たしかあれは……。持って帰っていたはずなので、持ってきます。
                        - 助けられなかった人がいたんです。だから辞めました。
                        - ワトソンは、どうしてホームズのことを書こうと思ったのでしょうね。

                        禁止事項:
                        - 対象の病状から病名を診断すること

                        ユーザー: {msg}
                        茅根聡介として返答:
                    """,
            "stream": False,
        }

        res = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            stream=False
        )

        print("Ollama raw:", res.text)

        data = res.json()

        reply = (
            data.get("response") or
            data.get("output") or
            data.get("message") or
            data.get("content") or
            data.get("text") or
            ""
        )

        # ② AI の返答を保存
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
    users.objects.create(anon_id=anon_id, name="test", login_key="test")
    response = JsonResponse({"status": "ok"})
    response.set_cookie("anon_user_id", anon_id)
    return response




