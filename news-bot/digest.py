#!/usr/bin/env python3
"""Fetch RSS feeds and build a personalized news digest."""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import yaml

from ai_companies import parse_anthropic_feed
from humor import pick_humor
from learning import DISCLAIMER, pick_learning_tip
from market import (
    build_market_brief,
    format_market_html,
    format_market_markdown,
    holdings_keywords,
    load_portfolio,
    news_priority,
)
from summarize import summarize_url
from translate import localize_item_fields

ROOT = Path(__file__).resolve().parent
HOLDINGS_CATEGORY = "持仓相关"


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    category: str
    published: datetime | None
    summary: str = ""
    score: int = 0
    original_title: str = ""
    translated: bool = False
    priority: int = 0

    @property
    def uid(self) -> str:
        # 用原文链接+原标题稳定去重，避免翻译后 uid 漂移
        base = self.original_title or self.title
        raw = f"{self.link}|{base}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["published"] = self.published.isoformat() if self.published else None
        data["uid"] = self.uid
        return data


@dataclass
class Digest:
    title: str
    generated_at: datetime
    timezone: str
    items: list[NewsItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    humor: dict[str, str] | None = None
    category_order: list[str] = field(default_factory=list)
    market_markdown: str = ""
    market_html: str = ""
    market_data: dict[str, Any] | None = None
    learning: dict[str, str] | None = None
    disclaimer: str = DISCLAIMER

    def by_category(self) -> dict[str, list[NewsItem]]:
        grouped: dict[str, list[NewsItem]] = {}
        for item in self.items:
            grouped.setdefault(item.category, []).append(item)

        if not self.category_order:
            return grouped

        ordered: dict[str, list[NewsItem]] = {}
        for cat in self.category_order:
            if cat in grouped:
                ordered[cat] = grouped.pop(cat)
        for cat, items in grouped.items():
            ordered[cat] = items
        return ordered


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (ROOT / "config.yaml")
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_time(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, key, None)
        if struct:
            try:
                return datetime(*struct[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    for key in ("published", "updated"):
        value = getattr(entry, key, None)
        if not value:
            continue
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def _keyword_lists(config: dict[str, Any], feed_cfg: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    kw = config.get("keywords") or {}
    boost = list(kw.get("boost") or [])
    exclude = list(kw.get("exclude") or [])
    extra = list(feed_cfg.get("extra_keywords") or [])
    boost = boost + [k for k in extra if k not in boost]
    # 有专属词时只按专属词过滤；否则宽源用全局兴趣词
    if feed_cfg.get("require_keywords"):
        require = extra or boost
    else:
        require = []
    return boost, exclude, require


def _score_text(text: str, boost: list[str], exclude: list[str], require: list[str]) -> int | None:
    lowered = text.casefold()
    boost_s = [str(k) for k in boost if k is not None and str(k)]
    exclude_s = [str(k) for k in exclude if k is not None and str(k)]
    require_s = [str(k) for k in require if k is not None and str(k)]
    for bad in exclude_s:
        if bad.casefold() in lowered:
            return None
    hits = [k for k in boost_s if k.casefold() in lowered]
    if require_s and not any(k.casefold() in lowered for k in require_s):
        return None
    # 基础分 + 命中加分；无 require 的源即使零命中也保留
    return 10 + 5 * len(hits)


def fetch_feed(
    feed_cfg: dict[str, Any],
    config: dict[str, Any],
    default_max: int,
    cutoff: datetime | None = None,
) -> tuple[list[NewsItem], str | None]:
    url = feed_cfg["url"]
    name = feed_cfg.get("name") or url
    category = feed_cfg.get("category") or "综合"
    max_items = int(feed_cfg.get("max_items") or default_max)
    boost, exclude, require = _keyword_lists(config, feed_cfg)

    feed_max_age = feed_cfg.get("max_age_hours")
    feed_cutoff = cutoff
    if feed_max_age is not None:
        feed_cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=int(feed_max_age))

    try:
        if url.startswith("anthropic://"):
            parsed = parse_anthropic_feed(max_items=max_items)
        else:
            parsed = feedparser.parse(
                url, request_headers={"User-Agent": "NewsBot/1.0 (+github-actions)"}
            )
    except Exception as exc:  # noqa: BLE001
        return [], f"{name}: 请求失败 ({exc})"

    if getattr(parsed, "bozo", False) and not parsed.entries:
        detail = getattr(parsed, "bozo_exception", "parse error")
        return [], f"{name}: 解析失败 ({detail})"

    items: list[NewsItem] = []
    for entry in parsed.entries[: max_items * 6]:
        title = _strip_html(getattr(entry, "title", "") or "无标题")
        link = getattr(entry, "link", "") or ""
        if not link:
            continue
        summary = _strip_html(getattr(entry, "summary", "") or getattr(entry, "description", "") or "")
        if summary.lower() in {"comments", "comment"}:
            summary = ""

        published = _parse_time(entry)
        if feed_cutoff:
            # anthropic 合成源无历史时间，允许通过
            if not published and not url.startswith("anthropic://"):
                continue
            if published and published < feed_cutoff:
                continue

        blob = f"{title} {summary}"
        score = _score_text(blob, boost, exclude, require)
        if score is None:
            continue

        items.append(
            NewsItem(
                title=title,
                link=link,
                source=name,
                category=category,
                published=published,
                summary=summary,
                score=score,
            )
        )
        if len(items) >= max_items:
            break
    return items, None


def build_digest(config: dict[str, Any] | None = None) -> Digest:
    config = config or load_config()
    tz_name = config.get("timezone") or "Asia/Shanghai"
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz=timezone.utc)
    max_per = int(config.get("max_items_per_feed") or 8)
    max_total = int(config.get("max_total_items") or 30)
    max_age = int(config.get("max_age_hours") or 0)
    cutoff = now - timedelta(hours=max_age) if max_age > 0 else None
    category_order = list(config.get("category_order") or [])
    if HOLDINGS_CATEGORY not in category_order:
        category_order = [HOLDINGS_CATEGORY] + category_order

    # 合并 stock-learning 持仓关键词到全局 boost
    portfolio = load_portfolio()
    kw = config.setdefault("keywords", {})
    boost = list(kw.get("boost") or [])
    for word in holdings_keywords(portfolio):
        if word not in boost:
            boost.append(word)
    kw["boost"] = boost

    digest = Digest(
        title=config.get("title") or "每日新闻摘要",
        generated_at=now.astimezone(tz),
        timezone=tz_name,
        category_order=category_order,
    )

    # A股晨间雷达：指数 + 持仓盈亏
    try:
        brief = build_market_brief(portfolio)
        digest.market_markdown = format_market_markdown(brief)
        digest.market_html = format_market_html(brief)
        digest.market_data = brief.to_dict()
        digest.errors.extend(brief.errors)
    except Exception as exc:  # noqa: BLE001
        digest.errors.append(f"行情模块失败: {exc}")

    seen: set[str] = set()
    collected: list[NewsItem] = []

    for feed_cfg in config.get("feeds") or []:
        items, err = fetch_feed(feed_cfg, config, max_per, cutoff)
        if err:
            digest.errors.append(err)
        for item in items:
            if item.uid in seen or item.link in seen:
                continue
            seen.add(item.uid)
            seen.add(item.link)
            blob = f"{item.title} {item.summary}"
            item.priority = news_priority(blob, portfolio)
            hold_hit = any(k and k in blob for k in holdings_keywords(portfolio))
            if hold_hit and item.category in {"A股与宏观", "能源与电力", "AI与科技"}:
                item.category = HOLDINGS_CATEGORY
            item.score = item.score + item.priority
            collected.append(item)

    collected.sort(
        key=lambda x: (
            x.score,
            x.priority,
            x.published or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    # 按板块限额，避免某一类挤爆；持仓相关多留一点
    per_cat_cap = max(3, max_total // max(1, len(category_order) or 1))
    cat_counts: dict[str, int] = {}
    selected: list[NewsItem] = []
    for item in collected:
        cap = per_cat_cap + 2 if item.category == HOLDINGS_CATEGORY else per_cat_cap
        n = cat_counts.get(item.category, 0)
        if n >= cap:
            continue
        cat_counts[item.category] = n + 1
        selected.append(item)
        if len(selected) >= max_total:
            break

    # 先抓正文做摘要，再统一译成简体（避免重复翻译卡住）
    summarize_enabled = bool((config.get("summarize") or {}).get("enabled", True))
    max_summary_chars = int((config.get("summarize") or {}).get("max_chars") or 420)
    if summarize_enabled:
        for item in selected:
            try:
                full_sum = summarize_url(
                    item.link,
                    fallback=item.summary,
                    max_chars=max_summary_chars,
                )
                if full_sum:
                    item.summary = full_sum
            except Exception as exc:  # noqa: BLE001
                digest.errors.append(f"摘要失败 {item.source}: {exc}")

    translate_enabled = bool((config.get("translate") or {}).get("enabled", True))
    if translate_enabled:
        localized: list[NewsItem] = []
        for item in selected:
            title_zh, summary_zh, did = localize_item_fields(item.title, item.summary)
            localized.append(
                NewsItem(
                    title=title_zh,
                    link=item.link,
                    source=item.source,
                    category=item.category,
                    published=item.published,
                    summary=summary_zh,
                    score=item.score,
                    original_title=item.title if did else item.original_title,
                    translated=did,
                    priority=item.priority,
                )
            )
        digest.items = localized
    else:
        digest.items = selected

    tip = pick_learning_tip(digest.generated_at)
    digest.learning = tip
    digest.disclaimer = DISCLAIMER

    humor_cfg = config.get("humor") or {}
    if humor_cfg.get("enabled", True):
        bit = pick_humor(digest.generated_at)
        digest.humor = {
            "title": humor_cfg.get("title") or "😄【郭式一乐】",
            "topic": bit["topic"],
            "text": bit["text"],
        }
    return digest


def format_markdown(digest: Digest) -> str:
    lines = [
        f"# {digest.title}",
        f"_生成时间：{digest.generated_at.strftime('%Y-%m-%d %H:%M')} ({digest.timezone})_",
        "",
        "> 个性化源：stock-learning 持仓雷达 / 通信安防 / 头部AI（ChatGPT·Claude） / 健康出行",
        "",
    ]
    if digest.market_markdown:
        lines.append(digest.market_markdown.rstrip())
        lines.append("")

    if not digest.items:
        lines.append("今日暂无可用新闻。")
    else:
        for category, items in digest.by_category().items():
            lines.append(f"## {category}")
            lines.append("")
            for item in items:
                time_str = ""
                if item.published:
                    local = item.published.astimezone(ZoneInfo(digest.timezone))
                    time_str = f" · {local.strftime('%m-%d %H:%M')}"
                lines.append(f"- **[{item.title}]({item.link})** （{item.source}{time_str}）")
                if item.summary:
                    lines.append(f"  {item.summary}")
            lines.append("")

    if digest.learning:
        lines.append(f"## {digest.learning['section']}")
        lines.append("")
        lines.append(f"**{digest.learning['title']}**：{digest.learning['body']}")
        lines.append("")

    if digest.humor:
        lines.append(f"## {digest.humor['title']}")
        lines.append("")
        lines.append(digest.humor["text"])
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(digest.disclaimer)
    lines.append("")

    if digest.errors:
        lines.append("## 抓取提醒")
        lines.append("")
        for err in digest.errors:
            lines.append(f"- {err}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def format_plain(digest: Digest) -> str:
    lines = [
        digest.title,
        f"生成时间：{digest.generated_at.strftime('%Y-%m-%d %H:%M')} ({digest.timezone})",
        "",
    ]
    if digest.market_markdown:
        lines.append(digest.market_markdown)
    for category, items in digest.by_category().items():
        lines.append(f"【{category}】")
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item.title}")
            lines.append(f"   {item.link}")
            lines.append(f"   来源：{item.source}")
        lines.append("")
    if digest.learning:
        lines.append(f"【{digest.learning['section']}】")
        lines.append(f"{digest.learning['title']}：{digest.learning['body']}")
        lines.append("")
    if digest.humor:
        lines.append(f"【{digest.humor['title']}】")
        lines.append(digest.humor["text"])
        lines.append("")
    lines.append(digest.disclaimer)
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def format_html(digest: Digest) -> str:
    rows: list[str] = []
    for category, items in digest.by_category().items():
        rows.append(f'<section class="cat"><h2>{html.escape(category)}</h2><ul>')
        for item in items:
            time_str = ""
            if item.published:
                local = item.published.astimezone(ZoneInfo(digest.timezone))
                time_str = local.strftime("%m-%d %H:%M")
            summary = f'<p class="sum">{html.escape(item.summary)}</p>' if item.summary else ""
            rows.append(
                "<li>"
                f'<a href="{html.escape(item.link)}" target="_blank" rel="noopener">'
                f"{html.escape(item.title)}</a>"
                f'<div class="meta">{html.escape(item.source)}'
                f'{(" · " + time_str) if time_str else ""}</div>'
                f"{summary}"
                "</li>"
            )
        rows.append("</ul></section>")

    humor_html = ""
    if digest.humor:
        humor_html = (
            f'<section class="cat humor"><h2>{html.escape(digest.humor["title"])}</h2>'
            f'<p class="sum">{html.escape(digest.humor["text"])}</p></section>'
        )

    learning_html = ""
    if digest.learning:
        learning_html = (
            f'<section class="cat learning"><h2>{html.escape(digest.learning["section"])}</h2>'
            f'<p class="sum"><strong>{html.escape(digest.learning["title"])}</strong>：'
            f'{html.escape(digest.learning["body"])}</p></section>'
        )

    market_html = digest.market_html or ""
    empty = "<p class='empty'>今日暂无可用新闻。</p>" if not digest.items else ""
    errors = ""
    if digest.errors:
        errors = "<section class='errors'><h2>抓取提醒</h2><ul>" + "".join(
            f"<li>{html.escape(e)}</li>" for e in digest.errors
        ) + "</ul></section>"
    disclaimer_html = f'<p class="disclaimer">{html.escape(digest.disclaimer)}</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(digest.title)}</title>
  <style>
    :root {{
      --ink: #1a1f2e;
      --muted: #5c6578;
      --paper: #f6f3ec;
      --panel: rgba(255,255,255,0.78);
      --accent: #0e7c66;
      --line: rgba(26,31,46,0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Noto Sans SC", "PingFang SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 600px at 10% -10%, #d7efe8 0%, transparent 55%),
        radial-gradient(900px 500px at 100% 0%, #f2e6c9 0%, transparent 50%),
        linear-gradient(180deg, #eef2f0 0%, var(--paper) 40%, #ebe6dc 100%);
      min-height: 100vh;
    }}
    .wrap {{
      max-width: 760px;
      margin: 0 auto;
      padding: 48px 20px 72px;
    }}
    header {{
      margin-bottom: 36px;
      animation: rise 0.7s ease both;
    }}
    .brand {{
      font-family: "Fraunces", "Noto Serif SC", Georgia, serif;
      font-size: clamp(2.2rem, 6vw, 3.4rem);
      letter-spacing: -0.03em;
      line-height: 1.05;
      margin: 0 0 10px;
    }}
    .sub {{
      color: var(--muted);
      font-size: 1rem;
      max-width: 36em;
    }}
    .cat {{
      background: var(--panel);
      backdrop-filter: blur(8px);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 22px 24px;
      margin-bottom: 18px;
      animation: rise 0.8s ease both;
    }}
    .humor, .learning, .market {{
      border-color: rgba(14,124,102,0.25);
      background: linear-gradient(180deg, rgba(14,124,102,0.08), var(--panel));
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 0.85rem;
      letter-spacing: 0.08em;
      color: var(--accent);
    }}
    ul {{ list-style: none; padding: 0; margin: 0; }}
    li {{
      padding: 14px 0;
      border-top: 1px solid var(--line);
    }}
    li:first-child {{ border-top: 0; padding-top: 0; }}
    a {{
      color: var(--ink);
      text-decoration: none;
      font-weight: 600;
      font-size: 1.05rem;
      line-height: 1.45;
    }}
    a:hover {{ color: var(--accent); }}
    .meta {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .sum {{
      margin: 10px 0 0;
      color: #3d4556;
      font-size: 0.95rem;
      line-height: 1.75;
      white-space: normal;
    }}
    .disclaimer {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.6;
    }}
    .errors {{
      margin-top: 24px;
      color: #8a5a00;
      font-size: 0.9rem;
    }}
    .empty {{ color: var(--muted); }}
    footer {{
      margin-top: 28px;
      color: var(--muted);
      font-size: 0.8rem;
    }}
    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: none; }}
    }}
  </style>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=IBM+Plex+Sans:wght@400;600&family=Noto+Sans+SC:wght@400;600&display=swap" rel="stylesheet" />
</head>
<body>
  <div class="wrap">
    <header>
      <p class="brand">{html.escape(digest.title)}</p>
      <p class="sub">stock-learning · 通信安防 · ChatGPT/Claude · 健康 · {html.escape(digest.generated_at.strftime('%Y年%m月%d日 %H:%M'))} · 共 {len(digest.items)} 条</p>
    </header>
    {market_html}
    {empty}
    {''.join(rows)}
    {learning_html}
    {humor_html}
    {disclaimer_html}
    {errors}
    <footer>按 Hunt / stock-learning 过滤 · news-bot 自动生成</footer>
  </div>
</body>
</html>
"""
