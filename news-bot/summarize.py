#!/usr/bin/env python3
"""Fetch article body and build a concise summary (language-agnostic)."""

from __future__ import annotations

import re
import urllib.request
from urllib.parse import urlparse

import trafilatura

_SENT_SPLIT = re.compile(r"(?<=[。！？.!?;；])\s*")


def _fetch_text(url: str) -> str:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 NewsBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            downloaded = resp.read()
    except Exception:
        return ""
    if not downloaded:
        return ""
    try:
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            favor_recall=False,
            deduplicate=True,
            url=url,
        )
    except Exception:
        return ""
    return (text or "").strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def summarize_text(text: str, max_chars: int = 420) -> str:
    text = _clean(text)
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p and p.strip()]
    if not parts:
        return text[: max_chars - 1] + "…"

    out: list[str] = []
    size = 0
    chineseish = any("\u4e00" <= ch <= "\u9fff" for ch in text[:40])
    for part in parts:
        if len(part) < 8:
            continue
        add = len(part) + (1 if out else 0)
        if size + add > max_chars and out:
            break
        out.append(part)
        size += add
        if size >= max_chars * 0.75 and len(out) >= 2:
            break
    summary = "".join(out) if chineseish else " ".join(out)
    if not summary:
        summary = text[: max_chars - 1] + "…"
    elif len(summary) > max_chars:
        summary = summary[: max_chars - 1] + "…"
    return summary


def summarize_url(url: str, fallback: str = "", max_chars: int = 420) -> str:
    """Return extractive summary; keep original language (caller may translate)."""
    host = urlparse(url).netloc.lower()
    fallback = _clean(fallback)

    # RSS 摘要已经够长时，优先用它，避免慢速抓页
    if len(fallback) >= 220:
        return summarize_text(fallback, max_chars=max_chars)

    if any(x in host for x in ("twitter.com", "x.com")):
        return summarize_text(fallback, max_chars=max_chars)

    body = _fetch_text(url)
    raw = body if len(body) > len(fallback) else fallback
    return summarize_text(raw, max_chars=max_chars)
