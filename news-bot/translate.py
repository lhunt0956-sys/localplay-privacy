#!/usr/bin/env python3
"""Detect English / Traditional Chinese and normalize to Simplified Chinese."""

from __future__ import annotations

import re
import time
from functools import lru_cache

import zhconv

_HAN = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")

# 引擎按稳定性排序；失败自动换下一个
_ENGINES = ("bing", "google", "alibaba", "sogou")


def is_mostly_english(text: str) -> bool:
    if not text or not text.strip():
        return False
    latin = len(_LATIN.findall(text))
    han = len(_HAN.findall(text))
    if latin < 8:
        return False
    # 拉丁字母明显多于汉字，视为英文
    return latin >= max(12, han * 2)


def to_simplified(text: str) -> str:
    if not text:
        return text
    return zhconv.convert(text, "zh-cn")


@lru_cache(maxsize=512)
def _translate_cached(text: str) -> str:
    import translators as ts

    last_err: Exception | None = None
    for engine in _ENGINES:
        try:
            out = ts.translate_text(
                text,
                translator=engine,
                from_language="en",
                to_language="zh",
            )
            if out and out.strip() and out.strip() != text.strip():
                return to_simplified(out.strip())
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    if last_err:
        raise last_err
    return text


def localize_text(text: str) -> tuple[str, bool]:
    """Return (localized_text, translated_from_english)."""
    if not text:
        return text, False
    text = text.strip()
    if is_mostly_english(text):
        # 翻译接口对过长文本不稳，摘要截断后再译
        chunk = text if len(text) <= 450 else text[:447] + "..."
        try:
            translated = _translate_cached(chunk)
            time.sleep(0.15)  # 轻微限速，降低被拒概率
            return translated, True
        except Exception:
            return to_simplified(text), False
    return to_simplified(text), False


def localize_item_fields(title: str, summary: str) -> tuple[str, str, bool]:
    new_title, t1 = localize_text(title)
    new_summary, t2 = localize_text(summary) if summary else ("", False)
    return new_title, new_summary, t1 or t2
