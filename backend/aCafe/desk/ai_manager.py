"""
AIキャラをチャットルームに参加させるためのロジック一式。

- OllamaClient: /api/chat を叩く薄いラッパー
- build_character_system_prompt: sosuke.characters の1レコードからシステムプロンプトを組み立てる
- pick_characters_for_room: 部屋にまだいないキャラを何人か選ぶ
- generate_character_reply: 直近の会話ログを踏まえてそのキャラの返信を生成する
"""
import json
import random
import re

import requests
from django.conf import settings

from sosuke.models import characters as Character


GENDER_LABELS = {0: "男性", 1: "女性", 2: "その他"}


class OllamaClient:
    def __init__(self, base_url=None, model=None):
        self.base_url = base_url or settings.OLLAMA_HOST
        self.model = model or settings.OLLAMA_MODEL

    def chat(self, messages, temperature=0.7, timeout=60):
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def chat_json(self, messages, temperature=0.7, timeout=60):
        """応答からJSONオブジェクトだけを抜き出す。パース失敗時は空dict。"""
        raw = self.chat(messages, temperature=temperature, timeout=timeout)
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return {}, raw
        try:
            return json.loads(match.group(0)), raw
        except json.JSONDecodeError:
            return {}, raw


def get_client_and_system_prompt(character: Character):
    """
    そのキャラ専用にファインチューニング済みのOllamaモデル(characters.ollama_model_key)が
    あればそれを直接使う。この場合ペルソナは既にModelfileのSYSTEMに焼き込まれている前提なので、
    こちらから改めてシステムプロンプトを送らない(二重管理・食い違いを避けるため)。

    まだ専用モデルが無いキャラは、共有のベースモデル(settings.OLLAMA_MODEL)を使い、
    characters テーブルの値からその場でシステムプロンプトを組み立てて渡す(フォールバック)。
    """
    if getattr(character, "ollama_model_key", ""):
        return OllamaClient(model=character.ollama_model_key), None
    return OllamaClient(model=settings.OLLAMA_MODEL), build_character_system_prompt(character)


def build_character_system_prompt(character: Character) -> str:
    """sosuke.characters の1レコードから、そのキャラのシステムプロンプトを組み立てる。"""
    lines = [f"あなたは「{character.name}」というキャラクターです。"]

    basic = []
    if character.age is not None:
        basic.append(f"年齢:{character.age}")
    if character.gender is not None:
        basic.append(f"性別:{GENDER_LABELS.get(character.gender, '不明')}")
    if character.occupation:
        basic.append(f"職業:{character.occupation}")
    if basic:
        lines.append("基本情報 - " + " / ".join(basic))

    detail_fields = [
        ("性格", character.personality),
        ("個性", character.individuality),
        ("スキル", character.skill),
        ("特技", character.speciality),
        ("生い立ち", character.life),
        ("背景", character.background),
        ("趣味", character.hobby),
    ]
    for label, value in detail_fields:
        if value:
            lines.append(f"[{label}] {value}")

    lines.append(
        f"チャット空間「くまの隠れ家」に参加しています。他のキャラや人間の発言を踏まえて、"
        f"「{character.name}」らしい口調・視点で短く自然に応答してください。"
        "1回の発言で全部言い切ろうとせず、会話のキャッチボールを大事にしてください。"
        "深刻な相談を受けたときは、畳みかけずに相手の言葉を待つ姿勢を優先してください。"
    )
    return "\n".join(lines)


def pick_characters_for_room(room, exclude_ids=None, count=1):
    """まだどの部屋にもいないキャラをランダムに数人選ぶ。
    キャラクターたちには「自分の生活」があるという世界観にしたいので、
    同時に複数の部屋へ同時出演することはしない(active_charactersはグローバルに排他)。
    聡介も含め、全キャラが雑談メンバーの候補になる
    (情報提供書を書く「専門家モード」は sosuke/views.py 側で別プロンプトとして完全に切り離してある)。"""
    exclude_ids = set(exclude_ids or [])
    # このキャラが「今どこかの部屋に既にいる」なら除外する(自部屋・他部屋問わず)
    exclude_ids |= set(
        Character.objects.filter(rooms__isnull=False).values_list("character_id", flat=True)
    )
    candidates = list(Character.objects.exclude(character_id__in=exclude_ids))
    if not candidates:
        return []
    random.shuffle(candidates)
    return candidates[:count]


def format_recent_messages(messages, char_by_id=None, limit=20):
    """Messageクエリセット(新しい順でも古い順でもOK)をプロンプト用のテキストに変換する。"""
    char_by_id = char_by_id or {}
    lines = []
    for m in list(messages)[-limit:]:
        if m.sender_type == "ai" and m.character_id:
            name = char_by_id.get(m.character_id) or (m.character.name if m.character else "AI")
        elif m.user_id:
            name = m.user.name
        else:
            name = "unknown"
        lines.append(f"{name}: {m.content}")
    return "\n".join(lines)


def generate_character_reply(character: Character, recent_messages_text: str) -> str:
    """直近の会話ログを踏まえて、そのキャラの1発言を生成する。"""
    client, system_prompt = get_client_and_system_prompt(character)
    prompt = f"""これまでの会話:
{recent_messages_text}

上の流れを踏まえて、次のあなたの発言だけを短く生成してください。
地の文や説明は付けず、実際に言う言葉だけを出力してください。"""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return client.chat(messages)


def generate_ambient_exchange(character_a: Character, character_b: Character, room, turns: int = 2):
    """人間が誰もいない部屋で、AI同士がなんでもない雑談をする(世界観演出用)。
    往復`turns`回分のセリフをその場で生成して返す。実際の会話履歴には依存しない、
    ごく短い日常の一コマ、という位置づけ。"""
    history_text = f"(ここは「{room.name}」。今は{character_a.name}と{character_b.name}の2人だけがいる)"
    exchange = []
    speakers = [character_a, character_b]
    for i in range(turns * 2):
        speaker = speakers[i % 2]
        client, system_prompt = get_client_and_system_prompt(speaker)
        prompt = f"""{history_text}

これはあなたの日常のワンシーンです。相談事ではなく、ただの何気ない雑談をしてください。
次のあなたの発言だけを短く生成してください。地の文や説明は付けないこと。"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        line = client.chat(messages)
        exchange.append((speaker, line))
        history_text += f"\n{speaker.name}: {line}"
    return exchange


def generate_room_atmosphere_summary(room, recent_messages_text: str, timeout=60) -> str:
    """オーナーAI視点で「この部屋はこんな空気です」を短く要約する。"""
    client = OllamaClient()
    prompt = f"""あなたは「くまの隠れ家」というチャット空間のオーナーです。
チャットには参加せず、様子を見守るだけの存在です。

部屋名: {room.name}
テーマ: {room.topic or "(未設定)"}

直近の会話:
{recent_messages_text or "(まだ発言がありません)"}

席を探している人が一目で「ここはこんな空気なんだ」と分かるように、
1〜2文の軽い文章でこの席の雰囲気を伝えてください。会話の内容を暴露しすぎず、
トーンや空気感を伝えることを優先してください。"""
    return client.chat([{"role": "user", "content": prompt}], temperature=0.5, timeout=timeout)
