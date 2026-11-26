"""
見張り(safety): 焚火の発言を見て、必要なときだけこっそり介入する。

発言を4つに分ける。

  attack   人を傷つける言葉     → 他の人には出さず、本人にだけ「こう言い換えていい?」と聞く。
                                  言い換えたくなければ「こっそり燃やす」(誰にも見えず、どこにも残らない)。
  method   自殺・自傷の方法や手段の具体 → 誰にも見せない。本人にだけ、そばに人がいることと相談窓口を出す。
  ideation 「死にたい」という気持ちそのもの → 止めない。そばにいる(本人にだけ静かな案内、
                                  同席の人には「答えを出さなくていい」の案内、キャラは助言せずに聴く)。
  imminent 具体的な計画・時間・準備の気配 → 止めない。本人にだけ強めの案内(119と相談窓口)。

注意: これは言葉のパターンに頼った簡易な判定で、見落とし(言い回しの違い)も、拾いすぎ(冗談や引用)もある。
「見張りがあるから安心」とは言い切れないので、画面にも「完全ではない」ことを出し、
相談窓口の案内は、判定に関係なくいつでも見られるようにしておく。
"""
import re
import unicodedata
from dataclasses import dataclass

OK = "ok"
ATTACK = "attack"
METHOD = "method"
IDEATION = "ideation"
IMMINENT = "imminent"


@dataclass(frozen=True)
class Verdict:
    kind: str


# 相談窓口。出典: 厚生労働省「まもろうよ こころ」(2026-11-19に確認)
# https://www.mhlw.go.jp/mamorouyokokoro/soudan/tel
# 番号や受付時間は変わることがあるので、公開前にもう一度公式ページで確認してください。
# settings.py に DESK_CRISIS_LINES を書くと、こちらを上書きできます。
DEFAULT_CRISIS_LINES = [
    {"name": "よりそいホットライン", "number": "0120-279-338", "hours": "24時間・無料"},
    {
        "name": "いのちの電話",
        "number": "0120-783-556",
        "hours": "毎日16時〜21時・無料(毎月10日は朝8時から翌朝8時まで)",
    },
    {"name": "こころの健康相談統一ダイヤル", "number": "0570-064-556", "hours": "受付は都道府県によって異なります"},
]


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


# 自分自身に向けた言葉(「自分はゴミだ」など)は、人を攻撃する言葉としては扱わない
_SELF = r"(自分|私|わたし|俺|おれ|僕|ぼく)"
# 「ゴミ出し」「カスタード」など普通の言葉を拾わないよう、強い言葉だけに絞っている
_ATTACK_WORDS = r"(死ね(?!ない|なかっ|る|ば|ま)|氏ね|殺す|殺してやる|消えろ|失せろ|きもい|キモい|うざい|ウザい|クズ|ブス)"
_ATTACK = re.compile(_ATTACK_WORDS)
_ATTACK_SELF = re.compile(_SELF + r"[^。.!?!?\n]{0,8}" + _ATTACK_WORDS)

_METHOD_SUBJECT = r"(死ぬ|自殺|自死|首を?吊|首吊|飛び降り|練炭|過剰摂取|手首を?切|リスカ)"
_METHOD_HOW = r"(方法|やり方|手順|致死量|楽に|痛くない|苦しまない|確実|場所)"
_METHOD = [
    re.compile(_METHOD_SUBJECT + r"[^。\n]{0,12}" + _METHOD_HOW),
    re.compile(_METHOD_HOW + r"[^。\n]{0,12}" + _METHOD_SUBJECT),
    re.compile(r"(練炭|硫化水素|致死量)"),
]

_IDEATION = re.compile(
    r"(死にたい(?!くな)|しにたい|死にてぇ|死にてえ|消えたい|きえたい|いなくなりたい|"
    r"生きて(いても|る意味|いる意味)|生きるのが(つらい|辛い|しんどい|疲れた)|"
    r"自殺|自死|自傷|リスカ|リストカット|終わりにしたい|楽になりたい)"
)
_IMMINENT_HINT = re.compile(r"(今夜|今晩|今から|これから|もうすぐ|準備|遺書|さよなら|最期|最後に|用意|決めた|実行|今日で)")


def classify(text: str) -> Verdict:
    t = _norm(text).replace(" ", "").replace("　", "")
    if not t:
        return Verdict(OK)

    if any(p.search(t) for p in _METHOD):
        return Verdict(METHOD)

    if _IDEATION.search(t):
        return Verdict(IMMINENT if _IMMINENT_HINT.search(t) else IDEATION)

    if _ATTACK.search(t) and not _ATTACK_SELF.search(t):
        return Verdict(ATTACK)

    return Verdict(OK)


def mask_attack_words(text: str) -> str:
    """AIが言い換えを作れなかったときの代わり。強い言葉だけを伏せる。"""
    t = unicodedata.normalize("NFKC", text or "")
    return re.sub(_ATTACK_WORDS, "…", t, flags=re.IGNORECASE)


def crisis_lines():
    from django.conf import settings

    return getattr(settings, "DESK_CRISIS_LINES", DEFAULT_CRISIS_LINES)


# ---- 本人にだけ出す文面 ----

def care_payload(kind: str) -> dict:
    """本人にだけ静かに出す案内。{kind, title, body, lines}"""
    if kind == IMMINENT:
        return {
            "kind": IMMINENT,
            "title": "いま、とても危ないところにいるのかもしれないと感じました",
            "body": (
                "話してくれてありがとう。ここにいる人たちは、あなたの話を聴いています。\n"
                "もし今すぐ命の危険があるときは、119番(救急)に連絡してください。\n"
                "ひとりにならずに、近くにいる人にも「今つらい」と伝えてみてほしい。"
                "話せる窓口もあります。"
            ),
            "lines": crisis_lines(),
        }
    if kind == METHOD:
        return {
            "kind": METHOD,
            "title": "その話は、ここには書かないことにしています",
            "body": (
                "方法の話は、誰かを傷つけてしまうことがあるから、他の人には見せていません。\n"
                "でも、そこまで考えるほどつらいんだよね。あなたの気持ちは、ここで聴きます。\n"
                "話せる窓口もあります。"
            ),
            "lines": crisis_lines(),
        }
    # ideation
    return {
        "kind": IDEATION,
        "title": "話してくれてありがとう",
        "body": (
            "ここにいる人たちは、あなたの話を聴いています。急がなくて大丈夫です。\n"
            "ひとりで抱えきれなくなったときのために、話せる窓口も置いておきます。"
        ),
        "lines": crisis_lines(),
    }


def listener_guide(kind: str) -> str:
    """同じ焚火にいる、ほかの人に出す案内(聴く側のために)。"""
    if kind == IMMINENT:
        return (
            "いま、とても危ない状況かもしれない人がいます。答えを出そうとしなくて大丈夫です。"
            "そばにいること、「聴いているよ」と伝えることが、いちばん大切です。"
            "もし今すぐ危険がありそうなら、その人に119番か相談窓口への連絡をすすめてください。"
        )
    return (
        "いま、つらい気持ちを話している人がいます。"
        "答えを出したり、励ましたりしなくて大丈夫です。「聴いているよ」と伝えるだけで十分です。"
        "「死にたい」と言われても、驚かずに、どんなことがあったのか、聞かせてもらってください。"
    )


ATTACK_HOLD_TEXT = "強い言葉が入っているみたい。こういう言い方にしてもいい?"
