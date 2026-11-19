import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from desk.ai_manager import OllamaClient
from desk.services import get_or_create_guest
from .ai import generate_sosuke_reply
from .crisis import CRISIS_MESSAGE, CRISIS_RESOURCES, detect_suicidal_ideation
from .models import ChatLog, InformationSheet, Users

MAX_MESSAGE_LENGTH = 2000

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


@csrf_exempt
@require_http_methods(["POST"])
def chat(request):
    """
    マスター(聡介)との1対1チャット。
    ユーザーの発言に希死念慮・自殺念慮がうかがえる場合は crisis=true と相談窓口の一覧を返し、
    フロント側でチャット窓の下に表示する。判定はAIではなくキーワード照合で行う(crisis.py)。
    """
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    anon_id = body.get("anon_id")
    message = (body.get("message") or "").strip()
    if not anon_id:
        return JsonResponse({"error": "anon_id is required"}, status=400)
    if not message:
        return JsonResponse({"error": "message is required"}, status=400)
    if len(message) > MAX_MESSAGE_LENGTH:
        return JsonResponse({"error": "message is too long"}, status=400)

    user = get_or_create_guest(anon_id)
    crisis = detect_suicidal_ideation(message)

    history = list(ChatLog.objects.filter(user=user).order_by("-created_at")[:12])[::-1]
    ChatLog.objects.create(user=user, role="user", message=message)

    try:
        reply, provider, search_info = generate_sosuke_reply(history, message, crisis=crisis)
    except Exception:
        # AIが落ちていても、窓口の案内だけは必ず返す
        payload = {"error": "AIに接続できませんでした", "crisis": crisis}
        if crisis:
            payload.update({"crisis_message": CRISIS_MESSAGE, "resources": CRISIS_RESOURCES})
        return JsonResponse(payload, status=502)

    ChatLog.objects.create(user=user, role="sosuke", message=reply)

    payload = {"reply": reply, "provider": provider, "crisis": crisis}
    if search_info:
        payload["search"] = search_info
    if crisis:
        payload.update({"crisis_message": CRISIS_MESSAGE, "resources": CRISIS_RESOURCES})
    return JsonResponse(payload)
