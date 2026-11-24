from django.db import models


class SpaceRoom(models.Model):
    """3D空間の部屋。slugは接続用のID、nameは画面に出す部屋名"""

    slug = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.name