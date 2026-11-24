import math

from django.utils import timezone

# 火が弱まる速さ。この秒数で約37%まで弱まる(600秒 = 10分)
FIRE_TAU_SECONDS = 600.0

# 新しく部屋を作ったときの強さ
START_HEAT = 0.5

# 誰かが部屋にいる間は、これより弱くならない(熾火)
EMBER_HEAT = 0.12

# 誰もいなくて、これより弱くなったら「消えた」とみなす
EXTINGUISH_HEAT = 0.02


def decayed_heat(room, now=None) -> float:
    """最後に記録してからの経過時間で弱めた、今の火の強さ"""
    now = now or timezone.now()
    elapsed = max(0.0, (now - room.heat_updated_at).total_seconds())
    return room.heat * math.exp(-elapsed / FIRE_TAU_SECONDS)


def effective_heat(room, occupants: int, now=None) -> float:
    """人がいる間は熾火を下回らないようにした強さ"""
    heat = decayed_heat(room, now)
    if occupants > 0:
        heat = max(heat, EMBER_HEAT)
    return heat


def is_extinguished(room, occupants: int, now=None) -> bool:
    """火が消えて部屋を片付けてよい状態か"""
    if room.is_permanent or occupants > 0:
        return False
    return decayed_heat(room, now) < EXTINGUISH_HEAT


def chat_boost(text: str) -> float:
    """発言1回で火がどれだけ強くなるか(長い発言ほど少し強く、上限あり)"""
    return min(0.15, 0.04 + len(text) / 400)