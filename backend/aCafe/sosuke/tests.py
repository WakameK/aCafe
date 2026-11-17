import json

from django.test import TestCase, override_settings

from .crisis import detect_suicidal_ideation
from .models import ChatLog


class CrisisDetectionTests(TestCase):
    def test_detects_common_expressions(self):
        for text in ["もう死にたい", "消えたい…", "自殺を考えてる", "生きてる意味がない",
                     "死 に た い", "ﾘｽｶしちゃった", "I want to die"]:
            with self.subTest(text=text):
                self.assertTrue(detect_suicidal_ideation(text))

    def test_ignores_ordinary_text(self):
        for text in ["今日はコーヒーが美味しい", "眠れなくて困ってる", "死角になってた"]:
            with self.subTest(text=text):
                self.assertFalse(detect_suicidal_ideation(text))


@override_settings(SOSUKE_AI_PROVIDER="mock")
class ChatViewTests(TestCase):
    def post(self, body):
        return self.client.post("/api/sosuke/chat/", data=json.dumps(body), content_type="application/json")

    def test_normal_message(self):
        res = self.post({"anon_id": "test-anon", "message": "こんにちは"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["reply"])
        self.assertFalse(data["crisis"])
        self.assertNotIn("resources", data)
        self.assertEqual(ChatLog.objects.count(), 2)

    def test_crisis_message_returns_resources(self):
        res = self.post({"anon_id": "test-anon", "message": "もう消えたい"})
        data = res.json()
        self.assertTrue(data["crisis"])
        self.assertTrue(any(r.get("tel") == "0570-064-556" for r in data["resources"]))

    def test_requires_fields(self):
        self.assertEqual(self.post({"message": "hi"}).status_code, 400)
        self.assertEqual(self.post({"anon_id": "a"}).status_code, 400)


@override_settings(SOSUKE_AI_PROVIDER="auto", OLLAMA_HOST="http://127.0.0.1:1", SOSUKE_TIMEOUT=2)
class AutoFallbackTests(TestCase):
    def test_falls_back_to_mock_when_ollama_is_down(self):
        res = self.client.post(
            "/api/sosuke/chat/",
            data=json.dumps({"anon_id": "fallback", "message": "死にたい"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["provider"], "mock")
        self.assertTrue(data["crisis"])
        self.assertTrue(data["resources"])
