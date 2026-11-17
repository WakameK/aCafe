"""
マスター(茅根聡介)との1対1チャットの返答生成。

SOSUKE_AI_PROVIDER で接続先を切り替える:
- "ollama": Ollama にだけ繋ぐ(失敗したらエラー)
- "mock"  : AIを使わず、簡易なダミー応答を返す(動作確認用)
- "auto"  : Ollama を試し、繋がらなければダミー応答にフォールバック(デフォルト)

SOSUKE_MODEL を指定した場合は、そのモデル(例: kuma-counselor-v1)の Modelfile に
SYSTEM が焼き込まれている前提で、こちらからは人格のシステムプロンプトを送らない。
未指定なら共有の OLLAMA_MODEL に簡易の人格プロンプトを付けて使う。
"""
import logging
import random

import requests
from django.conf import settings

from desk.ai_manager import OllamaClient

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 12

FALLBACK_PERSONA = (
    "あなたは『喫茶くまの隠れ家』の店主、茅根聡介です。公認心理師で、今は休職中。"
    "落ち着いた口調で、評価や説教をせず、相手の言葉を受け止めて短く返してください。"
    "診断はせず、アドバイスを畳みかけず、相手のペースを大切にしてください。"
)

CRISIS_INSTRUCTION = (
    "相手は今、死にたい・消えたいほどのつらさを抱えている可能性があります。"
    "否定や励ましの押しつけはせず、話してくれたことを受け止め、安全を最優先にしてください。"
    "画面にはこころの相談窓口の案内が表示されています。"
    "人とつながれる窓口があることを、押しつけずにやさしく伝えてください。"
)

_MOCK_REPLIES = [
    "……そうでしたか。よかったら、もう少し聞かせてもらえますか。",
    "コーヒー、淹れておきますね。ゆっくりで大丈夫ですよ。",
    "うん、うん。それは気になりますよね。",
    "話してくれてありがとうございます。今はどんな気持ちに近いですか。",
    "急がなくていいですよ。ここは、そういう場所なので。",
]
_MOCK_CRISIS_REPLY = (
    "……話してくれて、ありがとうございます。それだけつらい中で、ここに来てくれたんですね。"
    "僕はここで聞いています。それと、すぐに人と話せる窓口も下に置いておきました。"
    "よかったら、そちらも頼ってみてください。"
)


def _mock_reply(user_message: str, crisis: bool) -> str:
    if crisis:
        return _MOCK_CRISIS_REPLY
    if not user_message.strip():
        return "……(マスターは静かにカップを拭いている)"
    return random.choice(_MOCK_REPLIES)


def _ollama_reply(history, user_message: str, crisis: bool) -> str:
    dedicated_model = getattr(settings, "SOSUKE_MODEL", "")
    client = OllamaClient(model=dedicated_model or settings.OLLAMA_MODEL)

    messages = []
    system_parts = []
    if not dedicated_model:
        system_parts.append(FALLBACK_PERSONA)
    if crisis:
        system_parts.append(CRISIS_INSTRUCTION)
    if system_parts:
        messages.append({"role": "system", "content": "\n".join(system_parts)})

    for log in history[-HISTORY_LIMIT:]:
        role = "user" if log.role == "user" else "assistant"
        messages.append({"role": role, "content": log.message})
    messages.append({"role": "user", "content": user_message})

    return client.chat(messages, timeout=getattr(settings, "SOSUKE_TIMEOUT", 120)).strip()


def generate_sosuke_reply(history, user_message: str, crisis: bool = False):
    """(返答テキスト, 実際に使ったプロバイダ名) を返す。"""
    provider = getattr(settings, "SOSUKE_AI_PROVIDER", "auto")

    if provider == "mock":
        return _mock_reply(user_message, crisis), "mock"

    try:
        reply = _ollama_reply(history, user_message, crisis)
        if reply:
            return reply, "ollama"
    except (requests.RequestException, KeyError, ValueError) as exc:
        if provider == "ollama":
            raise
        logger.warning("Ollama に接続できないためダミー応答に切り替えます: %s", exc)

    return _mock_reply(user_message, crisis), "mock"
