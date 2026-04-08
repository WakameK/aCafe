# =========================================================================
# データベース操作が出来るファイル
# =========================================================================

# =========================================================================
# データベース操作が出来るファイル
# =========================================================================

from django.db import models

# ======================================================================= 
# 住人のモデル
# =======================================================================
class characters(models.Model):
    character_id = models.AutoField(primary_key=True)   #自動で1から始まるIDを振る
    name = models.CharField(max_length=20)              #キャラクターの名前   
    age = models.IntegerField()                         #キャラクターの年齢
    gender = models.IntegerField()               #キャラクターの性別(0:男性, 1:女性, 2:その他)
    birthday = models.DateField()                       #キャラクターの誕生日
    height = models.IntegerField()                      #キャラクターの身長
    occupation = models.CharField(max_length=20)        #キャラクターの職業
    personality = models.CharField(max_length=1000)     #キャラクターの性格
    skill = models.CharField(max_length=1000)           #キャラクターのスキル
    speciality = models.CharField(max_length=1000)      #キャラクターの特技
    individuality = models.CharField(max_length=1000)   #キャラクターの個性
    background = models.CharField(max_length=1000)      #キャラクターの背景
    life = models.CharField(max_length=1000)            #キャラクターの生い立ち
    hobby = models.CharField(max_length=1000)           #キャラクターの趣味
    def __str__(self):
        return self.name

# ========================================================================
# 来談者(ユーザー)のモデル
# =========================================================================
class users(models.Model):
    user_id = models.AutoField(primary_key=True)                #自動で1から始まるIDを振る
    anon_id = models.CharField(max_length=50)                   #匿名ID(別デバイスからのログインを識別するため)固定で36文字です
    name = models.CharField(max_length=20)                      #ユーザーの名前
    login_key = models.CharField(max_length=100, null=True, blank=True)                #合言葉(別デバイスからのログイン)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name


# ========================================================================
# チャットログのモデル
# ========================================================================
class ChatLog(models.Model):
    user = models.ForeignKey(users, on_delete=models.CASCADE)
    role = models.CharField(max_length=20)  # "user" or "sosuke"
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)






# ========================================================================
# 情報提供書のモデル
# ========================================================================
class informationSheet(models.Model):
    sheet_id = models.AutoField(primary_key=True)                       #自動で1から始まるIDを振る
    user_id = models.ForeignKey(users, on_delete=models.CASCADE)        #ユーザーID（外部キー）
    severity = models.IntegerField()                                    #ユーザーの困り度(1~5の整数で大きいほど困っている)
    worries = models.CharField(max_length=1000)                         #ユーザーの悩み
    sleepStatus = models.CharField(max_length=1000)                     #ユーザーの睡眠状況
    appetiteStatus = models.CharField(max_length=1000)                  #ユーザーの食欲状況
    functioning = models.CharField(max_length=1000)                     #ユーザーの日常機能
    physicalSymptoms = models.CharField(max_length=1000)                #ユーザーの身体的症状
    mentalSymptoms = models.CharField(max_length=1000)                  #ユーザーの精神的症状
    consultationGoal = models.CharField(max_length=1000)                #薬の相談
    duration = models.CharField(max_length=500)                         #ユーザーの症状開始からの期間
    mainComplaint = models.CharField(max_length=1000)                   #ユーザーの主訴
    changesFromBefore = models.CharField(max_length=1000)               #ユーザーの症状発生以前からの変化
    cues = models.CharField(max_length=1000)                            #症状が発生するきっかけ
    timeZone = models.CharField(max_length=1000)                        #症状が発生する時間帯
    suicidalIdeation = models.CharField(max_length=1000)                #ユーザーの自殺念慮
    questions = models.CharField(max_length=1000)                       #ユーザーからの質問
    supportNeeded = models.CharField(max_length=1000)                   #ユーザーが次の診察で必要としている支援

    def __str__(self):
        return f"{self.user_id} - {self.character_id}"