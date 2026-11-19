"""
AIキャラを焚火に参加させるためのロジック一式。

- OllamaClient: /api/chat を叩く薄いラッパー
- build_character_system_prompt: sosuke.characters の1レコードからシステムプロンプトを組み立てる
- pick_characters_for_room: 焚火にまだいないキャラを何人か選ぶ
- generate_character_reply: 直近の会話ログを踏まえてそのキャラの返信を生成する
  (guidance を渡すと、「死にたい」気持ちを聴くときなど、その場に合わせた方針で返す)
- suggest_softer_text: 強い言葉を、本人の気持ちを残したまま和らげた言い方にする(見張り用)
- draft_public_note: 焚火の外に見せる「ひとこと」の下書きを作る(持ち主が承認するまで外には出ない)
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
        f"焚火を囲む空間「くまの隠れ家」に参加しています。他のキャラや人間の発言を踏まえて、"
        f"「{character.name}」らしい口調・視点で短く自然に応答してください。"
        "1回の発言で全部言い切ろうとせず、会話のキャッチボールを大事にしてください。"
        "深刻な相談を受けたときは、畳みかけずに相手の言葉を待つ姿勢を優先してください。"
    )
    return "\n".join(lines)


def pick_characters_for_room(room, exclude_ids=None, count=1):
    """まだどの焚火にもいないキャラをランダムに数人選ぶ。
    キャラクターたちには「自分の生活」があるという世界観にしたいので、
    同時に複数の焚火へ同時出演することはしない(active_charactersはグローバルに排他)。
    聡介も含め、全キャラが雑談メンバーの候補になる
    (情報提供書を書く「専門家モード」は sosuke/views.py 側で別プロンプトとして完全に切り離してある)。"""
    exclude_ids = set(exclude_ids or [])
    # このキャラが「今どこかの焚火に既にいる」なら除外する(自分の焚火・他の焚火問わず)
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


# 同じ焚火の人が「死にたい」気持ちを話しているときに、キャラが従う方針。
# 参考: 厚生労働省「自殺に傾いた人への対応の実践」(傾聴 → 問題の整理 → 危険性の確認 → 保護因子 → 専門機関へ)
# ここを変えるときは、「その気持ちは正しい」「仕方ない」と言わせないこと(死ぬことへの許可に聞こえるため)。
KEEPER_GUIDANCE = """いま、同じ焚火にいる人が「死にたい」という気持ちを話しています。次の方針で、2〜3文で短く返してください。質問は1回に1つだけです。

【基本】決めつけず、批判せず、聴く。相手の言ったことを短く繰り返して、事実と気持ちを受け止める。
- 「死にたいほどつらいんだね」のように、痛みを受け止める。ただし、その気持ちが「正しい」「仕方ない」とは言わない。
- 説得、励まし、助言の羅列、「死んではいけない」という禁止、「自殺しないと約束して」はしない。

【流れ】会話の様子を見て、次のうち今ふさわしい1つだけを選ぶ。
1. まだ理由を話していない → どんなことがあったのかを、話せる範囲で聞かせてほしいと尋ねる。
2. 理由を話してくれた → その理由を整理して受け止める(つらいことは、いくつも重なっていることが多い)。重なっているものがあれば、「ほかにもしんどいことはある?」と1つ尋ねる。
3. 死にたい気持ちが強そう・続いていそう → 責めずに、「今夜にも、という気持ちはある?」「何か準備していることはある?」のように、直接やさしく尋ねる。尋ねることで安心して話せることがある。
4. 気持ちが少し落ち着いてきた → 「今までそれでも思いとどまれたのは、何だったんだろう」「安心して話せる人はいる?」「また同じ気持ちになったら、どうしてる?」のうち1つを尋ねる(支えになっているものを、いっしょに探す)。

【してはいけないこと】
- 自殺の方法・手段・場所・道具には一切触れない(尋ねるのも、答えるのも)。
- 危険が差し迫っていそうなときは、秘密にせず、ひとりにならずに近くの人や相談窓口に話してほしいと、やさしく伝える。
- 最後は、「あなたはひとりじゃない。ここで一緒にいる」と、そばにいることを伝える。約束をするなら、「また話そう」「また来てね」の形にする。"""


def generate_character_reply(character: Character, recent_messages_text: str, guidance=None, timeout=60) -> str:
    """直近の会話ログを踏まえて、そのキャラの1発言を生成する。"""
    client, system_prompt = get_client_and_system_prompt(character)
    extra = f"\n\n{guidance}" if guidance else ""
    prompt = f"""これまでの会話:
{recent_messages_text}

上の流れを踏まえて、次のあなたの発言だけを短く生成してください。
地の文や説明は付けず、実際に言う言葉だけを出力してください。{extra}"""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return client.chat(messages, timeout=timeout)


def generate_ambient_exchange(character_a: Character, character_b: Character, room, turns: int = 2, timeout=30):
    """人間が誰もいない焚火で、AI同士がなんでもない雑談をする(世界観演出用)。
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
        line = client.chat(messages, timeout=timeout)
        exchange.append((speaker, line))
        history_text += f"\n{speaker.name}: {line}"
    return exchange


def suggest_softer_text(text: str, timeout=20) -> str:
    """強い言葉を、本人の気持ちを残したまま、人を傷つけにくい言い方にする(見張り用)。"""
    prompt = f"""次の発言には、人を傷つけるかもしれない強い言葉が入っています。
言いたい気持ち(怒り・悔しさ・つらさ)は消さずに、相手を攻撃しない言い方に直してください。
- 1〜2文で、元の発言と同じくらいの長さにする
- 説明や前置きは付けず、直した発言だけを出力する

発言: {text}"""
    out = OllamaClient().chat([{"role": "user", "content": prompt}], temperature=0.4, timeout=timeout)
    return (out or "").strip().strip("「」\"")[:300]


def draft_public_note(recent_messages_text: str, timeout=30) -> str:
    """
    焚火の外に見せる「ひとこと」の下書きを作る。持ち主が承認するまで、外には出ない。
    どんな悩みや話題の焚火なのかが伝わって、入りやすくなる文にする。
    """
    prompt = f"""あなたは焚火を見守る係です。チャットには参加しません。

直近の会話:
{recent_messages_text or "(まだ発言がありません)"}

この焚火に入ろうか迷っている人が、「どんな話をしているところか」「自分が入っても大丈夫そうか」が
分かるように、やわらかい1文(40字以内)で、いまの話題を伝えてください。
- 人の名前、場所、勤務先・学校名など、個人が特定できることは書かない
- 発言をそのまま引用しない
- 自傷・死・暴力などの具体的な表現は書かず、「つらい気持ちを話しています」のように言い換える
- 説明や前置きは付けず、その1文だけを出力する"""
    out = OllamaClient().chat([{"role": "user", "content": prompt}], temperature=0.4, timeout=timeout)
    return (out or "").strip().strip("「」\"")[:100]
