# =======================================================================
# desk's models.py  (画面では「焚火」と呼ぶ。コード上の名前は Room のまま)
#
# 設計メモ(詳しくは DESIGN.md):
#   - 焚火(Room)は誰でも起こせる。輪に入れる人数(capacity)は起こした人が決める。
#   - 火は発言や薪で大きくなり、時間とともに小さくなる。消えたら焚火ごと(発言も)消える。
#   - 人数は保存しない。Presence(接続ごとの記録)から「いま生きている接続」を数える。
# =======================================================================
from django.db import models
from django.utils import timezone

from sosuke.models import Users, characters  # 既存の匿名ユーザーモデル / キャラクターモデル


class Room(models.Model):
    KIND_AMBIENT = "ambient"  # 最初からAIたちがいる焚火(運営が用意する。消えない)
    KIND_USER = "user"        # ユーザーが起こす焚火(火が消えたら、焚火ごと消える)
    KIND_LEGACY = "legacy"    # 席数が固定だった頃の部屋(一覧に出さない。発言ログだけ残っている)
    KIND_CHOICES = [
        (KIND_AMBIENT, "ambient"),
        (KIND_USER, "user"),
        (KIND_LEGACY, "legacy"),
    ]

    MODE_QUIET = "quiet"   # AIは近くにいるだけで、呼ばれるまで話しかけない
    MODE_TALK = "talk"     # AIキャラが積極的に会話に参加する
    MODE_CHOICES = [
        (MODE_QUIET, "quiet"),
        (MODE_TALK, "talk"),
    ]

    name = models.CharField(max_length=100)
    topic = models.CharField(max_length=200, blank=True, default="")  # 起こした人が書くテーマ(任意)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_TALK)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_USER, db_index=True)

    # 焚火を起こした人(ユーザーが起こした焚火のみ)。定員などを変えられるのは持ち主だけ
    owner = models.ForeignKey(
        Users, null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_desks"
    )
    # 輪に入れる「人間」の数(AIキャラは数えない)。持ち主がいつでも変えられる
    capacity = models.PositiveSmallIntegerField(default=6)

    # --- 火 ---
    # fire_level は fire_updated_at の時点の値(0〜1)。いまの火の大きさは時間の経過分を引いて求める
    fire_level = models.FloatField(default=0.6)
    fire_updated_at = models.DateTimeField(default=timezone.now)
    # 「そろそろ終いにしようか」を言ったか(火が回復したら False に戻す)
    closing_announced = models.BooleanField(default=False)

    # --- 外から見える「ひとこと」 ---
    # 持ち主が承認した文だけが、焚火の外(一覧)に出る。空なら外には何も出さない
    public_note = models.CharField(max_length=120, blank=True, default="")
    # AIが書いた下書き。持ち主にだけ見せて、承認されたら public_note になる
    note_draft = models.CharField(max_length=200, blank=True, default="")
    note_draft_at = models.DateTimeField(null=True, blank=True)

    # 輪の様子(workerが発言の数から計算する): waiting=新しい人を待っていそう / insiders=内輪で盛り上がっている / quiet=静か
    welcome = models.CharField(max_length=12, blank=True, default="")

    # 現在この焚火にいるAIキャラ(複数可)
    active_characters = models.ManyToManyField(characters, blank=True, related_name="rooms")

    # 「一人でいる人のところにAIが来る」予定時刻。None なら予定なし(workerが管理する)
    ai_join_after = models.DateTimeField(null=True, blank=True)
    # AIだけの焚火で、次にAIが動く(入室・雑談・退室する)時刻(workerが管理する)
    ambient_next_at = models.DateTimeField(null=True, blank=True)

    last_active_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Presence(models.Model):
    """
    「いま、この焚火につながっている接続」の記録。1接続 = 1行。

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


class DrinkGift(models.Model):
    """焚火に置かれたもの(薪・コーヒーなど)。置くと火が少し大きくなる。"""
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="gifts")
    # 人間が置いたなら from_user、AIキャラが置いたなら from_character(どちらか一方)
    from_user = models.ForeignKey(
        Users, related_name="gifts_sent", on_delete=models.CASCADE, null=True, blank=True
    )
    from_character = models.ForeignKey(
        characters, related_name="gifts_sent", on_delete=models.CASCADE, null=True, blank=True
    )
    to_user = models.ForeignKey(
        Users, related_name="gifts_received", on_delete=models.CASCADE, null=True, blank=True
    )
    item_name = models.CharField(max_length=50, default="薪")
    message = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
