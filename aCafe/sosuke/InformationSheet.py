import json
import requests
from django.http import JsonResponse
from .models import ChatLog
# =======================================================================
# InformationSheet: 情報提供書の作成ロジック
# =========================================================================
conversation = get_conversation_json(user)

prompt = {
    f"""
        instruction": "以下の会話ログから相談シートを作成してください。
        相談シートは、ユーザーの悩みや状況を整理するためのものです。
        相談シートには以下の項目を含めてください。
        - ユーザーの悩みや相談内容
        - ユーザーの感情や気持ち
        - ユーザーの生活状況や背景
        - ユーザーの主訴や症状
        - その他、相談に役立つと思われる情報
        会話ログ:
        {conversation}"
    """,
    "conversation": conversation
}

response = call_llm_api(prompt)
reply = response.get("response", "")