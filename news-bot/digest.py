#!/usr/bin/env python3
"""Fetch RSS feeds and build a news digest."""

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

ROOT = Path(__file__).resolve().parent


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    category: str
    published: datetime | None
    summary: str = ""

    @property
    def uid(self) -> str:
        raw = f"{self.link}|{self.title}".encode("utf-8")
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

    def by_category(self) -> dict[str, list[NewsItem]]:
        grouped: dict[str, list[NewsItem]] = {}
        for item in self.items:
            grouped.setdefault(item.category, []).append(item)
        return grouped


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


def fetch_feed(feed_cfg: dict[str, Any], max_items: int) -> tuple[list[NewsItem], str | None]:
    url = feed_cfg["url"]
    name = feed_cfg.get("name") or url
    category = feed_cfg.get("category") or "综合"
    try:
        parsed = feedparser.parse(url, request_headers={"User-Agent": "NewsBot/1.0 (+github-actions)"})
    except Exception as exc:  # noqa: BLE001
        return [], f"{name}: 请求失败 ({exc})"

    if getattr(parsed, "bozo", False) and not parsed.entries:
        detail = getattr(parsed, "bozo_exception", "parse error")
        return [], f"{name}: 解析失败 ({detail})"

    items: list[NewsItem] = []
    for entry in parsed.entries[: max_items * 2]:
        title = _strip_html(getattr(entry, "title", "") or "无标题")
        link = getattr(entry, "link", "") or ""
        if not link:
            continue
        summary = _strip_html(getattr(entry, "summary", "") or getattr(entry, "description", "") or "")
        if summary.lower() in {"comments", "comment"}:
            summary = ""
        if len(summary) > 160:
            summary = summary[:157] + "..."
        items.append(
            NewsItem(
                title=title,
                link=link,
                source=name,
                category=category,
                published=_parse_time(entry),
                summary=summary,
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

    digest = Digest(
        title=config.get("title") or "每日新闻摘要",
        generated_at=now.astimezone(tz),
        timezone=tz_name,
    )

    seen: set[str] = set()
    collected: list[NewsItem] = []

    for feed_cfg in config.get("feeds") or []:
        items, err = fetch_feed(feed_cfg, max_per)
        if err:
            digest.errors.append(err)
        for item in items:
            if cutoff and item.published and item.published < cutoff:
                continue
            if item.uid in seen or item.link in seen:
                continue
            seen.add(item.uid)
            seen.add(item.link)
            collected.append(item)

    collected.sort(key=lambda x: x.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    digest.items = collected[:max_total]
    return digest


def format_markdown(digest: Digest) -> str:
    lines = [
        f"# {digest.title}",
        f"_生成时间：{digest.generated_at.strftime('%Y-%m-%d %H:%M')} ({digest.timezone})_",
        "",
    ]
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
    for category, items in digest.by_category().items():
        lines.append(f"【{category}】")
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item.title}")
            lines.append(f"   {item.link}")
            lines.append(f"   来源：{item.source}")
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

    empty = "<p class='empty'>今日暂无可用新闻。</p>" if not digest.items else ""
    errors = ""
    if digest.errors:
        errors = "<section class='errors'><h2>抓取提醒</h2><ul>" + "".join(
            f"<li>{html.escape(e)}</li>" for e in digest.errors
        ) + "</ul></section>"

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
      max-width: 34em;
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
    .cat:nth-child(2) {{ animation-delay: 0.05s; }}
    .cat:nth-child(3) {{ animation-delay: 0.1s; }}
    .cat:nth-child(4) {{ animation-delay: 0.15s; }}
    h2 {{
      margin: 0 0 14px;
      font-size: 0.85rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
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
      margin: 8px 0 0;
      color: #3d4556;
      font-size: 0.92rem;
      line-height: 1.55;
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
      animation: rise 1s ease both;
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
      <p class="sub">自动聚合 · {html.escape(digest.generated_at.strftime('%Y年%m月%d日 %H:%M'))} ({html.escape(digest.timezone)}) · 共 {len(digest.items)} 条</p>
    </header>
    {empty}
    {''.join(rows)}
    {errors}
    <footer>由 news-bot 自动生成 · 可配合 GitHub Actions 定时推送</footer>
  </div>
</body>
</html>
"""
