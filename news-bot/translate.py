#!/usr/bin/env python3
"""Detect English / Traditional Chinese and normalize to Simplified Chinese."""

from __future__ import annotations

import re

import zhconv

_HAN = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_ENGINES = ("bing", "google", "alibaba")
_CACHE: dict[str, str] = {}


def is_mostly_english(text: str) -> bool:
    if not text or not text.strip():
        return False
    latin = len(_LATIN.findall(text))
    han = len(_HAN.findall(text))
    if latin < 8:
        return False
    return latin >= max(12, han * 2)


def to_simplified(text: str) -> str:
    if not text:
        return text
    return zhconv.convert(text, "zh-cn")


def _translate_once(text: str) -> str:
    import translators as ts

    for engine in _ENGINES:
        try:
            out = ts.translate_text(
                text,
                translator=engine,
                from_language="en",
                to_language="zh",
                timeout=7,
            )
            if out and out.strip() and out.strip() != text.strip():
                return to_simplified(out.strip())
        except TypeError:
            # older translators without timeout kw
            try:
                out = ts.translate_text(
                    text,
                    translator=engine,
                    from_language="en",
                    to_language="zh",
                )
                if out and out.strip() and out.strip() != text.strip():
                    return to_simplified(out.strip())
            except Exception:
                continue
        except Exception:
            continue
    return text


def localize_text(text: str) -> tuple[str, bool]:
    if not text:
        return text, False
    text = text.strip()
    if not is_mostly_english(text):
        return to_simplified(text), False
    chunk = text if len(text) <= 420 else text[:417] + "..."
    if chunk in _CACHE:
        return _CACHE[chunk], True
    translated = _translate_once(chunk)
    if translated and translated != chunk:
        _CACHE[chunk] = translated
        return translated, True
    return to_simplified(text), False


def localize_item_fields(title: str, summary: str) -> tuple[str, str, bool]:
    new_title, t1 = localize_text(title)
    new_summary, t2 = localize_text(summary) if summary else ("", False)
    return new_title, new_summary, t1 or t2
