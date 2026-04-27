from django.db import models

# Create your models here.

# =======================================================================
# 彩花が作成した作品のモデル
# =======================================================================
class opus(models.Model):
    opus_id = models.AutoField(primary_key=True)   #自動で1から始まるIDを振る
    title = models.CharField(max_length=100)       #作品のタイトル
    content = models.TextField()                   #作品の内容
    created_at = models.DateTimeField(auto_now_add=True)  #作成日時