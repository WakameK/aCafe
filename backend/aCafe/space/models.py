from django.db import models
from django.utils import timezone


class SpaceRoom(models.Model):
    """3D空間の部屋。slugは接続用のID、nameは画面に出す部屋名"""

    slug = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    # 焚火の強さ(0.0〜1.0)と、その値を記録した時刻。
    # 実際の強さは記録時刻からの経過時間で弱めて計算する(space/fire.py)
    heat = models.FloatField(default=0.5)
    heat_updated_at = models.DateTimeField(default=timezone.now)

    # True の部屋は火が消えても削除しない
    is_permanent = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.name