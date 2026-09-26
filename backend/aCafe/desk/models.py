# =======================================================================
# desk'smodels.py
# =======================================================================
from django.db import models
from sosuke.models import Users  # 既存の匿名ユーザーモデル

# ====================================
# チャットルームとメッセージのモデル
# ====================================

class Room(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

class Message(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    user = models.ForeignKey(Users, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
