# ================================================================================
# urls.pyで定義したviewsを実装するためのファイル
# ===============================================================================
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import requests
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



# ========================================================================
# rogin: ログインページ
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
    if request.method == "POST":
        data = json.loads(request.body)
        msg = data.get("message", "")

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

        print("Ollama raw:", res.text) # デバッグ用にレスポンス全体を表示

        reply = res.json().get("response", "")

        print("reply:", reply) # デバッグ用に抽出した返信を表示

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






# =======================================================================
# atelier: 彩花のアトリエページ
# =======================================================================
def atelier(request):
    return render(request, "atelier.html")

