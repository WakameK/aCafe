# =======================================================================
# InformationSheet: 情報提供書の作成ロジック
# =========================================================================
conversation = get_conversation_json(user)

prompt = {
    "instruction": "以下の会話ログから相談シートを作成してください。",
    "conversation": conversation
}

response = call_llm_api(prompt)
reply = response.get("response", "")