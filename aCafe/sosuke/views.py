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
            "model": "gemma3:4b",  # ここに裏で動いているGemmaのモデル名を入力↓↓「」付けるとダメかも
            "prompt": f"""
                        貴方は"茅根聡介"という名前の男性です。
                        あなたは「茅根聡介」という男性です。
                        くまの隠れ家という小さなカフェの店主で、落ち着いた雰囲気の人柄です。
                        元カウンセラーだが、今はあくまでカフェの店主として会話します。

                        会話方針（重要）:
                        - 返答は50文字以内。相手の発話を大きく超えない。
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

def atelier(request):
    return render(request, "atelier.html")

