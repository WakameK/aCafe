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

    # 今この部屋に接続している人間の人数(WebSocket接続時/切断時にconsumerが増減させる)
    human_count = models.PositiveIntegerField(default=0)

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
