"""
マスター(聡介)が分からない言葉を調べるための Web 検索。

検索は自前の SearXNG(docker-compose の searxng サービス)経由で行う。
SearXNG が裏で Google・Bing・DuckDuckGo などに問い合わせ、結果をまとめて JSON で返す。

- WEB_SEARCH_PROVIDER: "searxng"(デフォルト) / "off"(検索しない)
- SEARXNG_URL       : SearXNG の URL(docker 内なら http://searxng:8080)

検索に失敗しても会話は止めない(空のリストを返し、検索なしで返答する)。
"""
import hashlib
import logging
import re

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 50
SNIPPET_LENGTH = 300
CACHE_SECONDS = 60 * 60

# 検索語に個人情報が混ざっていたら取り除く(AIの判定だけに頼らない保険)
_PERSONAL_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),              # メールアドレス
    re.compile(r"\d{2,4}-?\d{2,4}-?\d{3,4}"),            # 電話番号っぽい数字
    re.compile(r"〒?\d{3}-\d{4}"),                        # 郵便番号
]


def sanitize_query(query: str) -> str:
    """検索語から個人情報っぽい部分を除き、長さを制限する。"""
    if not isinstance(query, str):
        return ""
    for pattern in _PERSONAL_PATTERNS:
        query = pattern.sub(" ", query)
    query = re.sub(r"\s+", " ", query).strip()
    return query[:MAX_QUERY_LENGTH]


def _is_http_url(url) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def web_search(query: str, max_results=None):
    """検索して [{"title", "url", "content"}, ...] を返す。失敗時・無効時は []。"""
    if getattr(settings, "WEB_SEARCH_PROVIDER", "searxng") != "searxng":
        return []

    query = sanitize_query(query)
    if not query:
        return []

    max_results = max_results or getattr(settings, "WEB_SEARCH_MAX_RESULTS", 3)
    cache_key = "websearch:" + hashlib.sha1(f"{query}|{max_results}".encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            f"{settings.SEARXNG_URL.rstrip('/')}/search",
            params={"q": query, "format": "json", "language": "ja", "safesearch": 1},
            headers={"Accept": "application/json"},
            timeout=getattr(settings, "WEB_SEARCH_TIMEOUT", 8),
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Web検索に失敗しました(検索なしで続けます): %s", exc)
        return []

    results = []
    # 辞書的な説明(Wikipedia など)があれば最初に入れる
    for box in data.get("infoboxes", [])[:1]:
        content = (box.get("content") or "").strip()
        url = next((u.get("url") for u in box.get("urls", []) if _is_http_url(u.get("url"))), "")
        if content:
            results.append({"title": box.get("infobox", ""), "url": url, "content": content[:SNIPPET_LENGTH]})

    for item in data.get("results", []):
        if len(results) >= max_results:
            break
        content = (item.get("content") or "").strip()
        if not content or not _is_http_url(item.get("url")):
            continue
        results.append({
            "title": (item.get("title") or "").strip(),
            "url": item["url"],
            "content": content[:SNIPPET_LENGTH],
        })

    cache.set(cache_key, results, CACHE_SECONDS)
    return results
