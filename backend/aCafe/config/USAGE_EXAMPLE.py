"""
使用例：views.pyでの活用方法
"""

# ====== 使い方1: 標準的な活用 ======
from config.settings_loader import get_config

# APIの設定を取得
PIXAZO_URL = get_config('api.pixazo.url')
PIXAZO_MODEL = get_config('api.pixazo.model')
IMAGE_WIDTH = get_config('image.generation.width')
IMAGE_HEIGHT = get_config('image.generation.height')

# Cookie設定を取得
COOKIE_USER_ID_NAME = get_config('cookie.user_id_name')
COOKIE_MAX_AGE_SECONDS = get_config('cookie.max_age_days') * 24 * 60 * 60
DEFAULT_USER_NAME = get_config('cookie.default_user_name')


# ====== 使い方2: views.py内での直接使用（推奨） ======
def generate_image(prompt: str):
    """設定から値を取得して画像生成"""
    url = get_config('api.pixazo.url')
    model = get_config('api.pixazo.model')
    width = get_config('image.generation.width')
    height = get_config('image.generation.height')
    
    payload = {
        "model": model,
        "prompt": prompt,
        "width": width,
        "height": height
    }
    res = requests.post(url, json=payload)
    return res.json().get("url")


def get_recent_messages(user, limit=None):
    """デフォルトの limit は設定ファイルから取得"""
    if limit is None:
        limit = get_config('chat.recent_messages_limit', default=20)
    
    logs = ChatLog.objects.filter(user=user).order_by('-created_at')[:limit]
    messages = [log.message for log in logs if log.role == "user"]
    return "\n".join(messages)


# ====== 使い方3: models.pyやadmin.pyでの活用 ======
# models.pyの例：
# from config.settings_loader import get_config
# 
# class MyModel(models.Model):
#     date_format = get_config('chat.date_format')


# ====== 使い方4: テスト時の独立した設定 ======
# test_views.py の例：
# from config.settings_loader import ConfigLoader
# 
# test_config = ConfigLoader(env='testing')
# TEST_URL = test_config.get('api.pixazo.url')
