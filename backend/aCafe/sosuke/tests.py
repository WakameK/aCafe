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


# ===== マスターの調べもの(Web検索) =====
from unittest import mock

from . import ai as sosuke_ai
from .search import sanitize_query, web_search


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


SEARXNG_DATA = {
    "infoboxes": [{"infobox": "推し", "content": "人に薦めたいほど好きな人や物のこと。",
                   "urls": [{"url": "https://ja.wikipedia.org/wiki/推し"}]}],
    "results": [
        {"title": "推し活とは", "url": "https://example.com/oshi", "content": "推しを応援する活動のこと。"},
        {"title": "本文なし", "url": "https://example.com/empty", "content": ""},
        {"title": "危ないURL", "url": "javascript:alert(1)", "content": "xxx"},
    ],
}


@override_settings(WEB_SEARCH_PROVIDER="searxng", SEARXNG_URL="http://searxng.test:8080")
class WebSearchTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_sanitize_removes_personal_info(self):
        q = sanitize_query("山田 taro@example.com 090-1234-5678 推し活")
        self.assertNotIn("@", q)
        self.assertNotIn("1234", q)
        self.assertIn("推し活", q)
        self.assertLessEqual(len(sanitize_query("あ" * 200)), 50)

    def test_parses_results_and_skips_bad_ones(self):
        with mock.patch("sosuke.search.requests.get", return_value=_FakeResponse(SEARXNG_DATA)) as get:
            results = web_search("推し活 意味")
        self.assertEqual(get.call_args.kwargs["params"]["format"], "json")
        self.assertEqual([r["url"] for r in results],
                         ["https://ja.wikipedia.org/wiki/推し", "https://example.com/oshi"])

    def test_failure_returns_empty(self):
        import requests
        with mock.patch("sosuke.search.requests.get", side_effect=requests.ConnectionError("down")):
            self.assertEqual(web_search("推し活"), [])

    @override_settings(WEB_SEARCH_PROVIDER="off")
    def test_off_does_not_search(self):
        with mock.patch("sosuke.search.requests.get") as get:
            self.assertEqual(web_search("推し活"), [])
        get.assert_not_called()


@override_settings(SOSUKE_AI_PROVIDER="ollama", WEB_SEARCH_PROVIDER="searxng", SOSUKE_MODEL="")
class SosukeSearchFlowTests(TestCase):
    def post(self, message):
        return self.client.post("/api/sosuke/chat/", data=json.dumps({"anon_id": "s", "message": message}),
                                content_type="application/json")

    def test_searches_and_passes_note_to_reply(self):
        with mock.patch.object(sosuke_ai.OllamaClient, "chat_json",
                               return_value=({"search": True, "query": "推し活 意味"}, "")), \
             mock.patch.object(sosuke_ai, "web_search", return_value=[
                 {"title": "推し活とは", "url": "https://example.com/oshi", "content": "推しを応援する活動。"}]), \
             mock.patch.object(sosuke_ai.OllamaClient, "chat", return_value="推し活、いいですね。") as chat:
            res = self.post("最近推し活にハマってて")
        data = res.json()
        self.assertEqual(data["reply"], "推し活、いいですね。")
        self.assertEqual(data["search"]["query"], "推し活 意味")
        self.assertEqual(data["search"]["sources"][0]["url"], "https://example.com/oshi")
        last_user = chat.call_args.args[0][-1]["content"]
        self.assertIn("推しを応援する活動。", last_user)
        # 保存されるログには検索メモを混ぜない
        self.assertEqual(ChatLog.objects.filter(role="user").get().message, "最近推し活にハマってて")

    def test_no_search_when_not_needed(self):
        with mock.patch.object(sosuke_ai.OllamaClient, "chat_json", return_value=({"search": False}, "")), \
             mock.patch.object(sosuke_ai, "web_search") as search, \
             mock.patch.object(sosuke_ai.OllamaClient, "chat", return_value="そうでしたか。"):
            data = self.post("今日はちょっと疲れました").json()
        search.assert_not_called()
        self.assertNotIn("search", data)

    def test_no_search_in_crisis(self):
        with mock.patch.object(sosuke_ai.OllamaClient, "chat_json") as decide, \
             mock.patch.object(sosuke_ai.OllamaClient, "chat", return_value="話してくれてありがとう。"):
            data = self.post("もう消えたい").json()
        decide.assert_not_called()
        self.assertTrue(data["crisis"])
