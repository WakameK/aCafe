# =======================================================================
# desk'smodels.py
# =======================================================================
from django.db import models
from sosuke.models import Users, characters  # 既存の匿名ユーザーモデル / キャラクターモデル

# ====================================
# チャットルームとメッセージのモデル
# ====================================

class Room(models.Model):
    MODE_QUIET = "quiet"   # AIは近くにいるだけで、呼ばれるまで話しかけない
    MODE_TALK = "talk"     # AIキャラが積極的に会話に参加する
    MODE_CHOICES = [
        (MODE_QUIET, "quiet"),
        (MODE_TALK, "talk"),
    ]

    name = models.CharField(max_length=100)
    topic = models.CharField(max_length=200, blank=True, default="")  # 部屋のテーマ(任意)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_TALK)

    # オーナーAI(sosuke)が作る「この部屋はこんな空気です」の要約。定期的/入室時に再生成する。
    atmosphere_summary = models.TextField(blank=True, default="")
    atmosphere_updated_at = models.DateTimeField(null=True, blank=True)

    # 現在この部屋にいるAIキャラ(複数可)
    active_characters = models.ManyToManyField(characters, blank=True, related_name="rooms")

    # 「誰もいない部屋にAIキャラを入れる」ロジックの二重起動防止フラグ
    ai_join_scheduled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Message(models.Model):
    SENDER_HUMAN = "human"
    SENDER_AI = "ai"
    SENDER_CHOICES = [
        (SENDER_HUMAN, "human"),
        (SENDER_AI, "ai"),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="messages")
    # 人間の発言ならuser、AIキャラの発言ならcharacterを使う(どちらか一方だけ埋まる想定)
    user = models.ForeignKey(Users, on_delete=models.CASCADE, null=True, blank=True)
    character = models.ForeignKey(characters, on_delete=models.CASCADE, null=True, blank=True)
    sender_type = models.CharField(max_length=10, choices=SENDER_CHOICES, default=SENDER_HUMAN)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


# ====================================
# 在席(WebSocket接続ごとのリース)
# ====================================

class Presence(models.Model):
    """
    「今この部屋に人間が接続している」ことを表す記録。接続ごとに1行。
    カウンタの増減ではなく、last_seen が新しい行の数を在席数とする。
    これにより、サーバーやconsumerが異常終了してdisconnectが呼ばれなくても、
    しばらくすれば自動的に在席から外れる(幽霊で席が満席のままになるのを防ぐ)。
    """
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="presences")
    channel_name = models.CharField(max_length=200, unique=True)
    last_seen = models.DateTimeField()


# ====================================
# テーブル
# ====================================

class Table(models.Model):
    """
    店内のテーブル。話題ごとに作られ、人数の上限は無い(テーブルを繋げた1つの大きな空間のイメージ)。
    誰かが座っている間、そのテーブルに紐づくチャット空間(Room)に全員が合流する。

    - 利用者が話題を付けて作ったテーブルは、全員が離れたら閉じる
    - is_permanent のテーブルは常設。全員が離れても残り、次に座る人には新しいRoomを作る
    """
    name = models.CharField(max_length=30)   # テーブルの話題。例: "最近読んだ本"
    is_permanent = models.BooleanField(default=False)
    room = models.OneToOneField(
        Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="table"
    )
    # 最後に誰かが座った時刻。座ってからWebSocketが繋がるまでの間にテーブルが「空き」に見えないための予約として使う
    sat_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


# ====================================
# 飲み物・食べ物メタファーAPI(奢る/奢られる)
# ====================================

class DrinkGift(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="gifts")
    from_user = models.ForeignKey(Users, related_name="gifts_sent", on_delete=models.CASCADE)
    # to_userがNoneなら「部屋全体に奢る」を表す
    to_user = models.ForeignKey(
        Users, related_name="gifts_received", on_delete=models.CASCADE, null=True, blank=True
    )
    item_name = models.CharField(max_length=50, default="コーヒー")
    message = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
