import json
import requests
from django.http import JsonResponse
from .models import ChatLog,user
from .views import get_conversation_json,call_llm_api
# =======================================================================
# InformationSheet: 情報提供書の作成ロジック
# =========================================================================
conversation = get_conversation_json(user)

prompt = {
    "instruction": f"""
        以下の会話ログから相談シートを作成してください。
        相談シートは、ユーザーの悩みや状況を整理するためのものです。
            severity = models.IntegerField()                                    #ユーザーの困り度(1~5の整数で大きいほど困っている)
            worries = models.TextField()                         #ユーザーの悩み
            sleepStatus = models.TextField()                     #ユーザーの睡眠状況
            appetiteStatus = models.TextField()                  #ユーザーの食欲状況
            functioning = models.TextField()                     #ユーザーの日常機能
            physicalSymptoms = models.TextField()                #ユーザーの身体的症状
            mentalSymptoms = models.TextField()                  #ユーザーの精神的症状
            consultationGoal = models.TextField()                #薬の相談
            duration = models.TextField()                         #ユーザーの症状開始からの期間
            mainComplaint = models.TextField()                   #ユーザーの主訴
            changesFromBefore = models.TextField()               #ユーザーの症状発生以前からの変化
            cues = models.TextField()                            #症状が発生するきっかけ
            timeZone = models.TextField()                        #症状が発生する時間帯
            suicidalIdeation = models.TextField()                #ユーザーの自殺念慮
            questions = models.TextField()                       #ユーザーからの質問
            supportNeeded = models.TextField()                   #ユーザーが次の診察で必要としている支援

        会話ログ:
        {conversation}
    """,
    "conversation": conversation
}


response = call_llm_api(prompt)
reply = response.get("response", "")