#!/usr/bin/env python3
"""Fetch official / tracked updates from top AI companies."""

from __future__ import annotations

import re
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any
from xml.sax.saxutils import escape

import feedparser

_ANTHROPIC_NEWS = "https://www.anthropic.com/news"


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 NewsBot/1.0", "Accept": "text/html"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _title_from_slug(slug: str) -> str:
    words = slug.replace("-", " ").strip()
    return words[:1].upper() + words[1:] if words else slug


def _page_title(url: str) -> str:
    try:
        html = _http_get(url, timeout=12)
    except Exception:
        return ""
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"<title>([^<]+)</title>", html, re.I)
    if m:
        return re.sub(r"\s*[|\-].*$", "", m.group(1)).strip()
    return ""


def fetch_anthropic_news(max_items: int = 6) -> list[dict[str, str]]:
    html = _http_get(_ANTHROPIC_NEWS)
    slugs = list(dict.fromkeys(re.findall(r'href="(/news/[^"#?]+)"', html)))
    items: list[dict[str, str]] = []
    for path in slugs:
        if path.rstrip("/") == "/news":
            continue
        slug = path.rsplit("/", 1)[-1]
        link = "https://www.anthropic.com" + path
        title = _page_title(link) or _title_from_slug(slug)
        if not title.lower().startswith(("anthropic", "claude")):
            title = f"Anthropic / Claude：{title}"
        items.append(
            {
                "title": title,
                "link": link,
                "summary": "来自 Anthropic 官网 News 的更新。",
                "source": "Anthropic News",
            }
        )
        if len(items) >= max_items:
            break
    return items


def anthropic_as_rss(max_items: int = 6) -> str:
    """Build a minimal RSS string so the existing feedparser path can consume it."""
    items = fetch_anthropic_news(max_items=max_items)
    now = format_datetime(datetime.now(tz=timezone.utc))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<rss version=\"2.0\"><channel>",
        "<title>Anthropic News</title>",
        f"<link>{escape(_ANTHROPIC_NEWS)}</link>",
        "<description>Anthropic / Claude updates</description>",
    ]
    for it in items:
        parts.extend(
            [
                "<item>",
                f"<title>{escape(it['title'])}</title>",
                f"<link>{escape(it['link'])}</link>",
                f"<guid>{escape(it['link'])}</guid>",
                f"<pubDate>{now}</pubDate>",
                f"<description>{escape(it['summary'])}</description>",
                "</item>",
            ]
        )
    parts.append("</channel></rss>")
    return "\n".join(parts)


def parse_anthropic_feed(max_items: int = 6) -> Any:
    return feedparser.parse(anthropic_as_rss(max_items=max_items))
