from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from desk.ai_manager import OllamaClient
from .models import ChatLog, InformationSheet, Users

SHEET_FIELDS = [
    "severity", "worries", "sleepStatus", "appetiteStatus", "functioning",
    "physicalSymptoms", "mentalSymptoms", "consultationGoal", "duration",
    "mainComplaint", "changesFromBefore", "cues", "timeZone",
    "suicidalIdeation", "questions", "supportNeeded",
]


@csrf_exempt
@require_http_methods(["POST"])
def generate_information_sheet(request, user_id):
    """
    ユーザーとの会話ログから、「次の診察で話そうと思っていたのに忘れそうなこと」を
    整理した下書きを作る。狙いは臨床的な評価書を作ることではなく、ユーザー自身が
    薬のこと・日常の困りごとなどを診察の場で言い忘れないための備忘録。

    出力はあくまで会話から拾えた内容の下書きであり、専門家の診断や評価の代わりには
    ならない。特に suicidalIdeation の項目は、ユーザー自身が診察の場で伝える・
    人間の専門家が内容を確認する、という前提を崩さないこと。
    """
    try:
        user = Users.objects.get(pk=user_id)
    except Users.DoesNotExist:
        return JsonResponse({"error": "user not found"}, status=404)

    logs = ChatLog.objects.filter(user=user).order_by("created_at")
    if not logs.exists():
        return JsonResponse({"error": "no chat logs for this user"}, status=400)

    log_text = "\n".join(f"{log.role}: {log.message}" for log in logs)

    client = OllamaClient()
    prompt = f"""以下は「{user.name}」さんとの会話ログです。
この人が次の診察で「話したかったのに忘れてしまう」ことがないように、
会話の中で語られた薬のこと・日常の困りごと・気になっていることを整理してください。
ログに書かれていない・読み取れない項目は、正直に空文字にしてください(推測で埋めないこと)。

会話ログ:
{log_text}

出力は次のJSON形式のみ。他の文章は付けないでください。
{{
  "severity": <1〜5の整数。困り度、読み取れなければ0>,
  "worries": "...", "sleepStatus": "...", "appetiteStatus": "...",
  "functioning": "...", "physicalSymptoms": "...", "mentalSymptoms": "...",
  "consultationGoal": "...", "duration": "...", "mainComplaint": "...",
  "changesFromBefore": "...", "cues": "...", "timeZone": "...",
  "suicidalIdeation": "...", "questions": "...", "supportNeeded": "..."
}}"""

    data, raw_reply = client.chat_json([{"role": "user", "content": prompt}], temperature=0.3)
    if not data:
        return JsonResponse({"error": "failed to parse model output", "raw": raw_reply}, status=502)

    sheet_kwargs = {field: data.get(field, "") for field in SHEET_FIELDS if field != "severity"}
    try:
        severity = int(data.get("severity", 0) or 0)
    except (TypeError, ValueError):
        severity = 0

    sheet = InformationSheet.objects.create(user_id=user, severity=severity, **sheet_kwargs)

    return JsonResponse(
        {
            "sheet_id": sheet.sheet_id,
            "is_draft": True,
            "note": "これは会話から拾った下書きのメモです。実際の診察では、内容を見ながら自分の言葉で伝えてください。",
            **{field: getattr(sheet, field) for field in SHEET_FIELDS},
        },
        status=201,
    )
