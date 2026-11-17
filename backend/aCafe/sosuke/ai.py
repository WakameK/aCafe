"""
マスター(茅根聡介)との1対1チャットの返答生成。

SOSUKE_AI_PROVIDER で接続先を切り替える:
- "ollama": Ollama にだけ繋ぐ(失敗したらエラー)
- "mock"  : AIを使わず、簡易なダミー応答を返す(動作確認用)
- "auto"  : Ollama を試し、繋がらなければダミー応答にフォールバック(デフォルト)

SOSUKE_MODEL を指定した場合は、そのモデル(例: kuma-counselor-v1)の Modelfile に
SYSTEM が焼き込まれている前提で、こちらからは人格のシステムプロンプトを送らない。
未指定なら共有の OLLAMA_MODEL に簡易の人格プロンプトを付けて使う。

分からない言葉の調べもの(sosuke/search.py):
1. まず AI に「この発言に、調べないと正しく答えられない言葉があるか」を JSON で判定させる
2. あれば SearXNG で検索し、結果を「マスターだけが見ているメモ」として発言に添えて返答させる
希死念慮がうかがえるとき(crisis)は返答を遅らせないため検索しない。
"""
import logging
import random

import requests
from django.conf import settings

from desk.ai_manager import OllamaClient

from .search import sanitize_query, web_search

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

SEARCH_DECISION_PROMPT = """あなたは、喫茶店のマスターが返事をする前に「ネットで調べる必要があるか」を判断する係です。
お客さんの発言を読んで、次のルールで判断してください。

- 固有名詞・専門用語・薬や病気の名前・作品名・お店や地名・最近の出来事・新しい言葉など、
  正確な知識がないと正しく受け答えできない言葉があるときだけ search を true にする
- 気持ちの話・雑談・あいさつ・相談ごとそのものは false
- query には調べたい言葉だけを入れる(例: "レクサプロ 副作用"、"推し活 意味")
- お客さんの名前・住所・連絡先・勤め先など、個人を特定できる情報は query に絶対に入れない
- query は30文字以内

出力は次の JSON だけにしてください。説明文は付けないこと。
{"search": true または false, "query": "検索語(不要なら空文字)"}"""

MIN_LENGTH_FOR_SEARCH = 4

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


def _reply_model() -> str:
    return getattr(settings, "SOSUKE_MODEL", "") or settings.OLLAMA_MODEL


def decide_search_query(user_message: str) -> str:
    """調べる必要があれば検索語を、なければ空文字を返す。判定に失敗したら空文字。"""
    if getattr(settings, "WEB_SEARCH_PROVIDER", "searxng") == "off":
        return ""
    if len(user_message.strip()) < MIN_LENGTH_FOR_SEARCH:
        return ""

    # 判定は人格なしの「係」として行う(システムプロンプトで Modelfile の人格を一時的に置き換える)
    model = getattr(settings, "SEARCH_DECISION_MODEL", "") or _reply_model()
    client = OllamaClient(model=model)
    try:
        data, _raw = client.chat_json(
            [
                {"role": "system", "content": SEARCH_DECISION_PROMPT},
                {"role": "user", "content": f"お客さんの発言:\n{user_message}"},
            ],
            temperature=0,
            timeout=getattr(settings, "SEARCH_DECISION_TIMEOUT", 30),
        )
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.info("検索の判定ができなかったので検索せずに返答します: %s", exc)
        return ""

    if data.get("search") is not True:
        return ""
    return sanitize_query(data.get("query") or "")


def build_search_note(query: str, results) -> str:
    """検索結果を、発言に添える「マスターのメモ」にする。"""
    lines = [
        "",
        "",
        "(ここから下はお客さんの言葉ではなく、マスターだけが見ている調べもののメモです)",
        f"「{query}」をネットで調べた結果:",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}: {r['content']}")
    lines.append(
        "このメモは参考にとどめ、マスターらしい言葉で自然に返事をしてください。"
        "確かでないことは断定せず、薬や病気のことは主治医や薬剤師に確かめるよう促してください。"
        "検索結果の文章をそのまま読み上げたり、URL を並べたりしないでください。"
    )
    return "\n".join(lines)


def _ollama_reply(history, user_message: str, crisis: bool, search_note: str = "") -> str:
    dedicated_model = getattr(settings, "SOSUKE_MODEL", "")
    client = OllamaClient(model=_reply_model())

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
    # 専用モデルは Modelfile の SYSTEM に人格が入っているので、system を増やさず発言側にメモを添える
    messages.append({"role": "user", "content": user_message + search_note})

    return client.chat(messages, timeout=getattr(settings, "SOSUKE_TIMEOUT", 120)).strip()


def generate_sosuke_reply(history, user_message: str, crisis: bool = False):
    """(返答テキスト, 実際に使ったプロバイダ名, 調べもの) を返す。
    調べものは検索したときだけ {"query": ..., "sources": [{"title", "url"}, ...]}、しなければ None。"""
    provider = getattr(settings, "SOSUKE_AI_PROVIDER", "auto")

    if provider == "mock":
        return _mock_reply(user_message, crisis), "mock", None

    search_info = None
    search_note = ""
    if not crisis:
        query = decide_search_query(user_message)
        results = web_search(query) if query else []
        if results:
            search_note = build_search_note(query, results)
            search_info = {
                "query": query,
                "sources": [{"title": r["title"], "url": r["url"]} for r in results if r["url"]],
            }

    try:
        reply = _ollama_reply(history, user_message, crisis, search_note)
        if reply:
            return reply, "ollama", search_info
    except (requests.RequestException, KeyError, ValueError) as exc:
        if provider == "ollama":
            raise
        logger.warning("Ollama に接続できないためダミー応答に切り替えます: %s", exc)

    return _mock_reply(user_message, crisis), "mock", None
