# =======================================================================
# desk's models.py
#
# 設計メモ(詳しくは DESIGN.md):
#   - 「机」= Room。席数の固定は無く、誰でも作れる。定員(capacity)は机ごとに作成者が決める。
#   - 机の人数は保存しない。Presence(接続ごとの記録)から「いま生きている接続」を数える。
#   - 発言(Message)は消さない。机が片付けられても履歴はDBに残る(is_archived で一覧から外すだけ)。
# =======================================================================
from django.db import models
from django.utils import timezone

from sosuke.models import Users, characters  # 既存の匿名ユーザーモデル / キャラクターモデル


class Room(models.Model):
    KIND_AMBIENT = "ambient"  # 最初からAIたちがいる机(運営が用意する)
    KIND_USER = "user"        # ユーザーが作る机
    KIND_CHOICES = [
        (KIND_AMBIENT, "ambient"),
        (KIND_USER, "user"),
    ]

    MODE_QUIET = "quiet"   # AIは近くにいるだけで、呼ばれるまで話しかけない
    MODE_TALK = "talk"     # AIキャラが積極的に会話に参加する
    MODE_CHOICES = [
        (MODE_QUIET, "quiet"),
        (MODE_TALK, "talk"),
    ]

    name = models.CharField(max_length=100)
    topic = models.CharField(max_length=200, blank=True, default="")  # 机のテーマ(作成者が書く・任意)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_TALK)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_USER)

    # 机の持ち主(ユーザーが作った机のみ)。定員などを変えられるのは持ち主だけ
    owner = models.ForeignKey(
        Users, null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_desks"
    )
    # 同時に座れる「人間」の数(AIキャラは数えない)。持ち主がいつでも変えられる
    capacity = models.PositiveSmallIntegerField(default=6)

    # 片付けられた机。一覧には出ないが、発言ログはDBに残る
    is_archived = models.BooleanField(default=False, db_index=True)

    # 要約(話題と空気感)を机の外から見えるようにするか。持ち主が選べる
    show_atmosphere = models.BooleanField(default=True)
    summary_topic = models.CharField(max_length=100, blank=True, default="")  # 例: 仕事の疲れについて
    summary_mood = models.CharField(max_length=100, blank=True, default="")   # 例: 静かに寄り添う感じ
    atmosphere_updated_at = models.DateTimeField(null=True, blank=True)

    # 現在この机にいるAIキャラ(複数可)
    active_characters = models.ManyToManyField(characters, blank=True, related_name="rooms")

    # 「一人でいる人のところにAIが来る」予定時刻。None なら予定なし(workerが管理する)
    ai_join_after = models.DateTimeField(null=True, blank=True)
    # AIだけの机で、次にAIが動く(入室・雑談・退室する)時刻(workerが管理する)
    ambient_next_at = models.DateTimeField(null=True, blank=True)

    # 最後に人の出入りや発言があった時刻。誰もいないまま一定時間たった机を片付ける目安
    last_active_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Presence(models.Model):
    """
    「いま、この机につながっている接続」の記録。1接続 = 1行。

    人数カウンタを持つ代わりにこれを数える。サーバーが落ちた・回線が切れたなどで
    切断処理が走らなくても、last_seen が更新されなくなるので一定時間後に自動で数えなくなる。
    """
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="presences")
    user = models.ForeignKey(Users, on_delete=models.CASCADE, related_name="desk_presences")
    channel_name = models.CharField(max_length=255, unique=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now, db_index=True)

    def __str__(self):
        return f"{self.user_id}@{self.room_id}"


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
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["room", "id"])]


# ====================================
# 飲み物・食べ物メタファー(コーヒーを置く)
# ====================================

class DrinkGift(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="gifts")
    # 人間が置いたなら from_user、AIキャラが置いたなら from_character(どちらか一方)
    from_user = models.ForeignKey(
        Users, related_name="gifts_sent", on_delete=models.CASCADE, null=True, blank=True
    )
    from_character = models.ForeignKey(
        characters, related_name="gifts_sent", on_delete=models.CASCADE, null=True, blank=True
    )
    # to_userがNoneなら「机に置く(特定の誰かではない)」を表す
    to_user = models.ForeignKey(
        Users, related_name="gifts_received", on_delete=models.CASCADE, null=True, blank=True
    )
    item_name = models.CharField(max_length=50, default="コーヒー")
    message = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
